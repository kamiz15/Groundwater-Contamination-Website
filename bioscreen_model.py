import numpy as np
import scipy as sp


def bio_with_curve(
    thresholdConcentrationCthres,
    time,
    sourceThicknessH,
    sourceConcentrationc0,
    sourceWidthW,
    averageLinearGroundwaterVelocityv,
    longitudinalDispersivity_ax,
    horizontalTransverseDispersivity_ay,
    verticalTransverseDispersivity_az,
    effectiveDiffusionCoefficientDf,
    retardationFactorR,
    sourceDecayCoefficient_gamma,
    effectiveFirstOrderDecayCoefficient_lambda_eff,
    numberOfGaussPoints,
):
    # Directly aligned with legacy bioScreenFormula.py implementation
    y = 0.0
    z_1 = 0.0
    z = (z_1 + sourceThicknessH) / 2.0

    Dx = longitudinalDispersivity_ax * averageLinearGroundwaterVelocityv + effectiveDiffusionCoefficientDf
    Dy = horizontalTransverseDispersivity_ay * averageLinearGroundwaterVelocityv + effectiveDiffusionCoefficientDf
    Dz = verticalTransverseDispersivity_az * averageLinearGroundwaterVelocityv + effectiveDiffusionCoefficientDf

    vr = averageLinearGroundwaterVelocityv / retardationFactorR
    Dxr = Dx / retardationFactorR
    Dyr = Dy / retardationFactorR
    Dzr = Dz / retardationFactorR

    roots, weights = sp.special.roots_legendre(int(numberOfGaussPoints))

    def C(x):
        if x <= 1e-6:
            if y <= sourceWidthW / 2 and y >= -sourceWidthW / 2 and z <= sourceThicknessH and z >= z_1:
                return float(sourceConcentrationc0 * np.exp(-sourceDecayCoefficient_gamma * time))
            return 0.0

        a = sourceConcentrationc0 * np.exp(-sourceDecayCoefficient_gamma * time) * x / (8.0 * np.sqrt(np.pi * Dxr))
        bot = 0.0
        top = np.sqrt(np.sqrt(time))
        tau = (roots * (top - bot) + top + bot) / 2.0
        tau4 = tau ** 4

        x_term = np.exp(
            -(
                ((effectiveFirstOrderDecayCoefficient_lambda_eff - sourceDecayCoefficient_gamma) * tau4)
                + ((x - vr * tau4) ** 2) / (4.0 * Dxr * tau4)
            )
        ) / (tau ** 3)
        y_term = sp.special.erfc((y - sourceWidthW / 2) / (2.0 * np.sqrt(Dyr * tau4))) - sp.special.erfc(
            (y + sourceWidthW / 2) / (2.0 * np.sqrt(Dyr * tau4))
        )
        z_term = sp.special.erfc((z - sourceThicknessH) / (2.0 * np.sqrt(Dzr * tau4))) - sp.special.erfc(
            (z - z_1) / (2.0 * np.sqrt(Dzr * tau4))
        )
        term = x_term * y_term * z_term
        integrand = term * (weights * (top - bot) / 2.0)
        return float(a * 4.0 * np.sum(integrand))

    x_array = np.array([0.0])
    c_array = np.array([C(0.0)])
    x = 0.0

    # Same stopping rule as legacy implementation, with high cap safety
    max_steps = 100000
    steps = 0
    while C(x) >= thresholdConcentrationCthres and steps < max_steps:
        x += 1.0
        x_array = np.append(x_array, x)
        c_array = np.append(c_array, C(x))
        steps += 1

    lmax = float(x)
    return lmax, x_array, c_array


def bio(
    thresholdConcentrationCthres,
    time,
    sourceThicknessH,
    sourceConcentrationc0,
    sourceWidthW,
    averageLinearGroundwaterVelocityv,
    longitudinalDispersivity_ax,
    horizontalTransverseDispersivity_ay,
    verticalTransverseDispersivity_az,
    effectiveDiffusionCoefficientDf,
    retardationFactorR,
    sourceDecayCoefficient_gamma,
    effectiveFirstOrderDecayCoefficient_lambda_eff,
    numberOfGaussPoints,
):
    lmax, _, _ = bio_with_curve(
        thresholdConcentrationCthres,
        time,
        sourceThicknessH,
        sourceConcentrationc0,
        sourceWidthW,
        averageLinearGroundwaterVelocityv,
        longitudinalDispersivity_ax,
        horizontalTransverseDispersivity_ay,
        verticalTransverseDispersivity_az,
        effectiveDiffusionCoefficientDf,
        retardationFactorR,
        sourceDecayCoefficient_gamma,
        effectiveFirstOrderDecayCoefficient_lambda_eff,
        numberOfGaussPoints,
    )
    return f"{lmax:.2f}"
