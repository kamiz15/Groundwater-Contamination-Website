#%% Libraries 
import numpy as np
import matplotlib.pyplot as plt
import flopy
from pprint import pformat
import os
import math
import pandas as pd
import shutil

#%% Input data

ws = r"C:\Users\Orlando\Desktop\GWT"    #Working directory

data = pd.read_csv(os.path.join(ws, "input_vertical.csv"), delimiter=';', decimal='.') #.csv file containing the input data
print(data.head())

names = data["name"]                #name of each transport simulation
name = "Flow_model1"                #name of the flow simulation


Lx= data["Lx"].iloc[0]              #domain length [m]
#delr= float(data["delr"].iloc[0])   #cell size y-axis 
#ncol= int(np.round(Lx/delr, 0))     #number fo columns
nrow= 1
delc= 1

Lz = data["Lz"].iloc[0]        # total vertical thickness [m]
nlay= data["nlay"].iloc[0]   #number of layers
delv= Lz/nlay               #cell size y-axis 

ncol= data["ncol"].iloc[0]   #number fo columns
delr= Lx/ncol               #cell size x-axis 

#delv = float(data["delv"].iloc[0])  #cell size z-axis
#nlay = int(np.round(Lz/delv, 0))  # number of layers

top = 0.0                        #top elevation of the layer [m]
botm = np.linspace(top - delv, -Lz, nlay)

prsity = data["prsity"]         #porosity [-]
al = data["al"]                 #longitudal dispersivity [m]
at = data["at"]                 #transverse dispersivity [m]
atv = data["atv"]
gamma = data["gamma"].iloc[0]   #stoichiometric ratio [-]
Cd = data["Cd"]                 #Donor concentration [mg/L]
Ca = data["Ca"]                 #Acceptor concentration [mg/L]
h1 = data["h1"].iloc[0]         #hydraulic head left boundary [m]
h2 = data["h2"].iloc[0]         #hydraulic head rigth boundary [m]
hk = data["hk"].iloc[0]         #hydraulic conductivity [m/day]
vk = data["vk"].iloc[0]         #hydraulic conductivity [m/day]
#perlen = data["perlen"].iloc[0] #simulation time [day]
perlen = 100

#%%Courant and Peclet numbers

gradient = (h1 - h2) / Lx  #gradient of the domain [-]
q = hk * gradient          #darcy velocity [m/day]
v = q / prsity.iloc[0]     #seepage velocity [m/day]
D_long = al.iloc[0] * v    #Dispersion coefficient
Pe = v * delr / D_long     #Peclet number [-]

print(f"Peclet = {Pe:.3f}")

dt_target = delr / v       #target Courant = 1

nts = int(math.ceil(perlen / dt_target))      #number of time steps needed
print(f"Recommended dt ≈ {dt_target:.3f} days -> nstp = {nts}")

#%%File to save the plume lengths

out_csv = os.path.join(ws, "plume_length.csv")

if os.path.exists(out_csv):             #if the file exist, write the results on it
    df_plume = pd.read_csv(out_csv)
else:                                   #if the file did not exist, then is created
    df_plume = pd.DataFrame(columns=["sim_name", "gamma", "plume_length"])

#%%FLOW simulation

gwf_ws = os.path.join(ws, "gwf_base")         #Path to store the flow model
    
sim= flopy.mf6.MFSimulation(sim_name=name, sim_ws=gwf_ws)           #create simulation
tdis= flopy.mf6.ModflowTdis(sim, perioddata=[[perlen, nts, 1.0]])   #create tdis package
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

mm = flopy.plot.PlotMapView(model=gwf) #Plot Map view
mm.plot_grid()

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
#bdobj = gwf.output.budget()
#spdis = bdobj.get_data(text="DATA-SPDIS")[0]

#Plotting the flow simulation
fig, ax = plt.subplots(figsize=(15, 2))  
pmv = flopy.plot.PlotCrossSection(model=gwf, line={"row": nrow//2}, ax=ax)
c = pmv.plot_array(head, cmap="jet")
plt.colorbar(c, ax=ax, orientation="vertical", shrink=0.5)
plt.title("Head [m]")
plt.show()


#%% TRANSPORT simulation

for i in np.arange(0, len(names)):          #for all the simulation in the input file
    sim_name = str(names.iloc[i])           #transport simulation name
    run_dir = os.path.join(ws, f"run_{i}")  #path to store the transport files
    gamma = 3.5
    #for gamma in range(3,11):               #for gamma values from 3 to 10
    run_name = f"{sim_name}_{gamma}"    #simulation name + the gamma value evaluated
    simf = flopy.mf6.MFSimulation(sim_name=sim_name, sim_ws=run_dir)
    tdisf = flopy.mf6.ModflowTdis(simf, perioddata=[[perlen, nts, 1.0]])
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
    

    strt_conc = np.ones((nlay, nrow, ncol)) * float(Ca.iloc[i])
    ic = flopy.mf6.ModflowGwtic(gwt, strt=strt_conc)                #initial concentration for the whole domain = Ca

    sto = flopy.mf6.ModflowGwtmst(gwt, porosity=prsity[i])          #mobile storage and transfer
    adv = flopy.mf6.ModflowGwtadv(gwt, scheme= "TVD")               #advection
    alh = np.full((nlay, nrow, ncol), al.iloc[i])
    dsp = flopy.mf6.ModflowGwtdsp(gwt, alh=alh, ath1=at[i])         #dispersion
    #dsp = flopy.mf6.ModflowGwtdsp(gwt, alh=alh, atv=atv[i])
    
    ssm = flopy.mf6.ModflowGwtssm(gwt)                              #source and sink mixing 
    
    cnc_cells = []
    

    for k in range(1, nlay):
        cnc_cells.append(((k, 0, 5), (gamma * Cd.iloc[i]) +  Ca.iloc[i]))  #left boundary fixed donor concentration
    
    for l in range(0, ncol): 
        cnc_cells.append(((0, 0, l), Ca.iloc[i]))       #top boundary fixed aceptor concentration

            
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
    
    #Plume length plot generation
    conc = gwt.output.concentration().get_data()
    C0= 8
    
    fig, ax = plt.subplots(figsize=(15, 3))
    
    xsect = flopy.plot.PlotCrossSection(model=gwf, line={"row": nrow//2}, ax=ax)
    c = xsect.plot_array(conc, cmap="jet")
    cs = xsect.contour_array(conc, levels=[C0], colors='k')
    
    cbar = plt.colorbar(c, ax=ax, orientation="vertical")
    cbar.set_label("Concentration [mg/L]")
    cbar.ax.yaxis.set_label_position('left')

    ax.set_xlabel("Distance [m]")
    ax.set_ylabel("Elevation [m]")
    
    out_png = os.path.join(ws, f"Plume_{run_name}.png")
    plt.savefig(out_png, dpi=300, bbox_inches="tight")
    plt.close()
    
    plt.show()
    
    mask = conc >= C0
    x_coords = np.where(mask)[2] * delr
    max_x = np.max(x_coords)

    mask = (df_plume["sim_name"] == sim_name) & (df_plume["gamma"] == gamma) 
    if mask.any():
        df_plume.loc[mask, "plume_length"] = round(max_x, 2)
    else:
        df_plume.loc[len(df_plume)] = [sim_name, gamma, round(max_x, 2)]
    df_plume.to_csv(out_csv, index=False) #save the plume length in the .csv file
        
    src = os.path.join(run_dir, f"{run_name}.lst")
    dst = os.path.join(ws, f"{run_name}.lst")
    assert os.path.exists(src), f"Source listing file missing: {src}" #Move the.lst file
    shutil.move(src, dst)
    
    shutil.rmtree(run_dir) #delete the files in the folder