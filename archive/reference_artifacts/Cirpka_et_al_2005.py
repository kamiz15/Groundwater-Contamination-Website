
import scipy.special as sc


def cirpka_2005(Sw=10, Ath=0.1, Ca=8, Cd=5, Ga=3.5):

    """
    Cirpka et al. (2005) horizontal flow model

    Parameters
    ----------
    Sw : Source thickness [L]
    Ath : Transverse horizontal dispersivity [L]
    Ca : Reactant Concentration [M/L^3]
    Cd : Source Concentration [M/L^3]
    Ga : Stoichiometric coefficient of the reactant [-]
Returns
-------
Lm : Maximum length of the plume [L]

References
----------
Cirpka, et al. 2005
    """
    
    cf = Ca / (Ga * Cd + Ca)
    Lm = (Sw)**2 / (16*Ath*sc.erfcinv(cf)**2)

    print('Maximum length of the plume: {:.2f} m'.format(Lm))
    return Lm

cirpka_2005()