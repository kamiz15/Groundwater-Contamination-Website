#%% Libraries 
import numpy as np
import matplotlib.pyplot as plt
import flopy
from pprint import pformat
import os
import math
import pandas as pd
import shutil
from scipy.special import erfinv


#%% Input data

ws = r"C:\Users\User\Downloads"    #Working directory

data = pd.read_csv(os.path.join(ws, "input_horizontal_W-1.csv"), delimiter=';', decimal='.') #.csv file containing the input data
print(data.head())

names = "Sim_1"                         #name of each transport simulation
name = "Flow_model1"                    #name of the flow simulation

nlay= 1                                 #number of layer, for 2D horizonta case = 1

delc = float(data["grid_size"])
delr = delc

top = 0.0                               #top elevation of the layer [m]
botm = -1.0                             #bottom elevation of the layer [m]

al = float(data["al"])                  #longitudal dispersivity [m]
at = float(data["at"])                  #transverse dispersivity [m]
gamma = float(data["gamma"])            #stoichiometric ratio [-]
Cd = float(data["Cd"])                  #Donor concentration [mg/L]
Ca = float(data["Ca"])                  #Acceptor concentration [mg/L]

source_thickness = float(data["source_zone_length"])

source_segments = []

for i in range(1, 11):  #up to 10 segments

    start_col = f"source_start_{i}"
    end_col = f"source_end_{i}"

    if start_col in data.columns and end_col in data.columns:

        start = data[start_col].iloc[0]
        end = data[end_col].iloc[0]

        if pd.notna(start) and pd.notna(end):
            source_segments.append([float(start), float(end)])
            

prsity = 0.3                #porosity [-]
hk = 8.4              #hydraulic conductivity [m/day]
gradient = 0.0125           #gradient of the domain [-]

Ly= source_thickness * 5   #Domain thickness [m]

Lx = 1.5 * (source_thickness**2 ) / (16 *at*(erfinv(Ca/(gamma*Cd + Ca))**2))  #Analytical solution for horizontal source L [m].

ncol= int(Lx/delr)
nrow= int(Ly/delc)
        
#%%Courant and Peclet numbers

q = hk * gradient               #darcy velocity [m/day]
v = q / prsity                  #seepage velocity [m/day]
D_long = al * v                 #Dispersion coefficient
Pe = v * delr / D_long          #Peclet number [-]

perlen = int(Lx/v + 1000)     #Simulation time [day]
#perlen=1000

print(f"Peclet = {Pe:.3f}")

dt_target = 2*delr / v          #target Courant = 1

nts1 = int(math.ceil(perlen / dt_target))      #number of time steps needed
print(f"Recommended dt ≈ {dt_target:.3f} days -> nstp = {nts1}")

nts2     = 50                     #Max 50 timesteps
nts = min(nts1, nts2)

tsmult  = 1.0                    


h1= 20
h2= float(h1 - gradient * Lx)

#%%FLOW simulation

gwf_ws = os.path.join(ws, "gwf_base")         #Path to store the flow model
    
sim= flopy.mf6.MFSimulation(sim_name=name, sim_ws=gwf_ws)           #create simulation
tdis= flopy.mf6.ModflowTdis(sim, perioddata=[[perlen, nts, tsmult]])   #create tdis package
#ims= flopy.mf6.ModflowIms(sim)                                      #create iterative model solution
ims = flopy.mf6.ModflowIms(
    sim,
    print_option="SUMMARY",
    complexity="SIMPLE",
    outer_dvclose=1e-3,
    inner_dvclose=1e-3,
    outer_maximum=100,
    inner_maximum=200,
    relaxation_factor=0.97
)
gwf= flopy.mf6.ModflowGwf(sim, modelname=name)                      #create the groundwater flow model object

#create the discretization package
dis = flopy.mf6.ModflowGwfdis(
    gwf,
    nlay=nlay,
    nrow=nrow,
    ncol=ncol,
    delr=delr,
    delc=delc,
    top=top,
    botm=botm)


#Create the fixed head boundary condition
chd_cells = [] 
for j in range(nlay):
    for i in range(nrow):
        chd_cells.append([(j, i, 0), h1])       #First left column fixed head = h1
        chd_cells.append([(j, i, ncol-1), h2])  #last rigth column fixed head = h2
chd = flopy.mf6.ModflowGwfchd(gwf, stress_period_data={0: chd_cells}) 

#Create the initial conditions package
strt = np.ones((nlay, nrow, ncol), dtype=np.float32)* ((h1 + h2) / 2)
strt[:, :, 0]  = h1
strt[:, :, -1] = h2
ic = flopy.mf6.ModflowGwfic(gwf, strt=strt) 

#Hydraulic properties in the node property flow package
icelltype= 0 #Confined aquifer
npf = flopy.mf6.ModflowGwfnpf(
    gwf, save_specific_discharge=True, save_saturation=True, icelltype=icelltype, k=hk)

hname = f"{name}.hds" #Head info
cname = f"{name}.cbc" #Budget info
#Define the output control package
oc = flopy.mf6.ModflowGwfoc(
    gwf,
    budget_filerecord=cname,
    head_filerecord=hname,
    saverecord=[("HEAD", "ALL"), ("BUDGET", "ALL")])

gwf.name_file.save_flows = True         #to save flows for all packages that can save flows

sim.write_simulation()                  #write the model
success, buff = sim.run_simulation(report=True, silent=True)
assert success, pformat(buff)

head = gwf.output.head().get_data()


#Plotting the flow simulation
fig, ax = plt.subplots(figsize=(15, 2))  
pmv = flopy.plot.PlotMapView(model=gwf, layer=0, ax=ax)
c = pmv.plot_array(head, cmap="jet")
plt.colorbar(c, ax=ax, orientation="vertical", shrink=0.5)
plt.title("Head [m]")
plt.show()

#%% TRANSPORT simulation

sim_name = names                        #transport simulation name
run_dir = os.path.join(ws, f"run_{i}")  #path to store the transport files
run_name = f"{sim_name}_{gamma}"        #simulation name + the gamma value evaluated
simf = flopy.mf6.MFSimulation(sim_name=sim_name, sim_ws=run_dir)
tdisf = flopy.mf6.ModflowTdis(simf, perioddata=[[perlen, nts, tsmult]])
gwt = flopy.mf6.ModflowGwt(simf, modelname=run_name, save_flows=True)
imsf = flopy.mf6.ModflowIms(simf, linear_acceleration="bicgstab")

#create the discretization package
disf = flopy.mf6.ModflowGwtdis(
    gwt,
    nlay=nlay,
    nrow=nrow,
    ncol=ncol,
    delr=delr,
    delc=delc,
    top=top,
    botm=botm)


strt_conc = np.ones((nlay, nrow, ncol)) * 0
ic = flopy.mf6.ModflowGwtic(gwt, strt=strt_conc)                #initial concentration for the whole domain = Ca

sto = flopy.mf6.ModflowGwtmst(gwt, porosity=prsity)          #mobile storage and transfer
adv = flopy.mf6.ModflowGwtadv(gwt, scheme= "TVD")               #advection
alh = np.full((nlay, nrow, ncol), al)
dsp = flopy.mf6.ModflowGwtdsp(gwt, alh=alh, ath1=at)         #dispersion

ssm = flopy.mf6.ModflowGwtssm(gwt)                              #source and sink mixing 


cnc_cells = []

source_zone_start = (Ly - source_thickness) / 2

for start_y, end_y in source_segments:

    # Coordinates relative to source zone
    # -> coordinates in the complete model
    actual_start_y = source_zone_start + start_y
    actual_end_y = source_zone_start + end_y

    # Convert physical coordinates to MODFLOW row indices
    s_start = int(np.floor(actual_start_y / delc))
    s_end = int(np.ceil(actual_end_y / delc))

    # Add source cells along the left boundary
    for k in range(s_start, s_end):
        cnc_cells.append(
            ((0, k, 0), (gamma * Cd) + Ca)
        )
        
"""cnc_cells = []

n_cells = int(np.round(source_thickness / delc))
center_index = nrow // 2  #center
half_cells = n_cells // 2
if n_cells % 2 == 0:
    s_start = center_index - half_cells
    s_end = center_index + half_cells
else:
    s_start = center_index - half_cells
    s_end = center_index + half_cells + 1           #include the central cell

for k in range(s_start, s_end):
    cnc_cells.append(((0, k, 0), (gamma * Cd) + Ca))  #left boundary fixed donor concentration"""

for l in range(0, ncol): 
    cnc_cells.append(((0, 0, l), 0))       #top boundary fixed aceptor concentration
for r in range(0, ncol): 
    cnc_cells.append(((0, nrow-1, r), 0))  #bottom boundary fixed aceptor concentration


        
#create constant concentration package    
cnc = flopy.mf6.ModflowGwtcnc(gwt, stress_period_data={0: cnc_cells}, filename=f"{run_name}.cnc")

#link to flow model 
pd_fmi= [("GWFHEAD", os.path.join(gwf_ws, f"{name}.hds")),
             ("GWFBUDGET", os.path.join(gwf_ws, f"{name}.cbc"))]
fmi = flopy.mf6.ModflowGwtfmi(gwt, packagedata=pd_fmi)   
      
#Define the output control package
oc = flopy.mf6.ModflowGwtoc(gwt,
    budget_filerecord=f"{sim_name}_gwt.cbc",
    concentration_filerecord=f"{sim_name}.ucn",
    saverecord=[("CONCENTRATION", "ALL"), ("BUDGET", "ALL")])

#write and run the simulation
simf.write_simulation()
success, buff = simf.run_simulation(report=True, silent=True)
assert success, pformat(buff)    

    
#%% Plot
    
conc = gwt.output.concentration().get_data()
C0 = Ca

oxygen = np.ma.masked_where(conc[0] >= C0, C0 - conc[0])
donor  = np.ma.masked_where(conc[0] <= C0, (conc[0] - C0)/gamma)

extent = [0, conc.shape[2]*delr, 0, conc.shape[1]*delc]

fig, ax = plt.subplots(figsize=(12,4))
#fig.subplots_adjust(bottom=0.38)
fig.subplots_adjust(right=0.8)

im1 = ax.imshow(oxygen, cmap="Blues", vmin=0, vmax=Ca,
                origin="lower", extent=extent, aspect="auto", interpolation="nearest")

im2 = ax.imshow(donor, cmap="Reds", vmin=0, vmax=Cd,
                origin="lower", extent=extent, aspect="auto", interpolation="nearest")

cs = ax.contour(conc[0], [C0], colors="k", linewidths=2,
                extent=extent)

ax.set(xlabel="Distance [m]", ylabel="Distance [m]")

# colorbars on the right side
pos = ax.get_position()

# First colorbar: Ca
cax1 = fig.add_axes([
    pos.x1 + 0.02,   # x position (right of plot)
    pos.y0,   # y position
    0.015,            # width
    pos.height   # height
])

cb1 = fig.colorbar(im1, cax=cax1, orientation="vertical")
cb1.ax.set_title(r"$C_a$ [mg/L]", pad=10)


# Second colorbar: Cd
cax2 = fig.add_axes([
    pos.x1 + 0.1,   # further right
    pos.y0,
    0.015,
    pos.height
])

cb2 = fig.colorbar(im2, cax=cax2, orientation="vertical")
cb2.ax.set_title(r"$C_d$ [mg/L]", pad=10)


#Maximum plume length
xs = [pt[0] for seg in cs.allsegs[0] for pt in seg]
max_x = max(xs)

#Dashed line
ax.axvline(max_x, color="k", linestyle="--", linewidth=2,
           label=f"Plume length = {max_x:.1f} m")

ax.legend()

plt.show()
    

#%% Plot
    
conc = gwt.output.concentration().get_data()
C0 = Ca

oxygen = np.ma.masked_where(conc[0] >= C0, C0 - conc[0])
donor  = np.ma.masked_where(conc[0] <= C0, (conc[0] - C0)/gamma)

extent = [0, conc.shape[2]*delr, 0, conc.shape[1]*delc]

fig, ax = plt.subplots(figsize=(12,4))
fig.subplots_adjust(bottom=0.3)
#fig.subplots_adjust(right=0.8)

im1 = ax.imshow(oxygen, cmap="Blues", vmin=0, vmax=Ca,
                origin="lower", extent=extent, aspect="auto", interpolation="nearest")

im2 = ax.imshow(donor, cmap="Reds", vmin=0, vmax=Cd,
                origin="lower", extent=extent, aspect="auto", interpolation="nearest")

cs = ax.contour(conc[0], [C0], colors="k", linewidths=2,
                extent=extent)

ax.set(xlabel="Distance [m]", ylabel="Distance [m]")


#colorbars
pos = ax.get_position()
for y, im, txt in [(0.15, im1, r"$C_a$ [mg/L]"), (0.23, im2, r"$C_d$ [mg/L]")]:
    cb = fig.colorbar(
        im,
        cax=fig.add_axes([pos.x0+pos.width*0.15,
                          pos.y0-y,
                          pos.width*0.6,
                          0.02]),
        orientation="horizontal"
    )
    cb.ax.text(1.02, 0.5, txt, transform=cb.ax.transAxes, va="center")


#Maximum plume length
xs = [pt[0] for seg in cs.allsegs[0] for pt in seg]
max_x = max(xs)

#Dashed line
ax.axvline(max_x, color="k", linestyle="--", linewidth=2,
           label=f"Plume length = {max_x:.1f} m")

ax.legend()

plt.show()
