"""Shared plume-growth animation wiring for the numerical model panels.

The animation never re-runs a simulation: it masks an already-computed
concentration field to a growing fraction of the plume length and rebuilds the
Bokeh figure via :func:`plot_functions.plot_reactive_plume_growth_frame`, which
reuses the exact orientation handling and colour mappers of the static plot
(so the T6-corrected vertical orientation - source band at the top - is
preserved throughout the sweep).
"""
import panel as pn

from plot_functions import plot_reactive_plume_growth_frame, plot_reactive_plume_interactive

# Number of discrete frames the Player sweeps through (0 .. ANIM_FRAMES).
ANIM_FRAMES = 20


def make_growth_player(name="Plume growth"):
    """A reusable Player widget that drives a fraction in [0, 1]."""
    return pn.widgets.Player(
        name=name, start=0, end=ANIM_FRAMES, value=ANIM_FRAMES, step=1,
        interval=220, loop_policy="once", visible=False, sizing_mode="stretch_width",
    )


def fraction_for(frame):
    """Map a Player frame index to a [0, 1] growth fraction."""
    try:
        return max(0.0, min(1.0, float(frame) / float(ANIM_FRAMES)))
    except (TypeError, ValueError, ZeroDivisionError):
        return 1.0


def bind_growth_animation(graph_pane, player, plot_kwargs):
    """Wire ``player`` so that stepping it re-renders ``graph_pane`` at the
    matching growth fraction.

    ``plot_kwargs`` is the full keyword set accepted by
    :func:`plot_reactive_plume_growth_frame` *except* ``fraction`` (which is
    supplied per frame). Returns the watcher object so the caller can unwatch it
    on reset. The graph_pane is left showing the full (final) plume.
    """
    def _update(event):
        fraction = fraction_for(event.new)
        graph_pane.object = plot_reactive_plume_growth_frame(
            fraction=fraction, **plot_kwargs
        )

    watcher = player.param.watch(_update, "value")
    # Make sure the pane starts at the full plume (fraction 1.0).
    graph_pane.object = plot_reactive_plume_interactive(**plot_kwargs)
    player.value = player.end
    player.visible = True
    return watcher


def play_growth_once(graph_pane, plot_kwargs, frames=ANIM_FRAMES, interval=70):
    """Play the plume-growth sweep exactly once for visual effect, then settle on
    the full static plume. No manual Player control is shown; the sweep is driven
    by a periodic callback that stops itself at the final frame.

    Returns a holder ``{"cb": <PeriodicCallback|None>, "i": int}`` so the caller
    can cancel an in-flight sweep (e.g. when a new run starts) via ``stop_growth``.
    """
    holder = {"cb": None, "i": 0}
    graph_pane.object = plot_reactive_plume_growth_frame(fraction=0.0, **plot_kwargs)

    def _step():
        holder["i"] += 1
        if holder["i"] >= frames:
            # Final frame: the full, un-masked plume (static).
            graph_pane.object = plot_reactive_plume_interactive(**plot_kwargs)
            cb = holder.get("cb")
            if cb is not None:
                cb.stop()
                holder["cb"] = None
        else:
            graph_pane.object = plot_reactive_plume_growth_frame(
                fraction=fraction_for(holder["i"]), **plot_kwargs
            )

    try:
        holder["cb"] = pn.state.add_periodic_callback(_step, interval, start=True)
    except Exception:
        # No live document / event loop (e.g. unit tests, headless render):
        # skip the sweep and show the full static plume immediately.
        graph_pane.object = plot_reactive_plume_interactive(**plot_kwargs)
    return holder


def stop_growth(holder):
    """Cancel an in-flight one-shot growth sweep started by ``play_growth_once``."""
    if not holder:
        return
    cb = holder.get("cb")
    if cb is not None:
        try:
            cb.stop()
        except Exception:
            pass
        holder["cb"] = None


def reset_growth_animation(player, watcher_holder):
    """Stop/hide the player and detach any watcher previously stored in
    ``watcher_holder`` (a single-key dict ``{"watcher": ...}``)."""
    watcher = watcher_holder.get("watcher")
    if watcher is not None:
        try:
            player.param.unwatch(watcher)
        except (ValueError, KeyError):
            pass
        watcher_holder["watcher"] = None
    player.visible = False
    try:
        player.value = player.end
    except Exception:
        pass
