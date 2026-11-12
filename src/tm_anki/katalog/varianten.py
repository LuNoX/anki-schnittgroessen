"""Vorzeichen-Varianten bekannter Systeme: trainieren Faser- und x1-Konvention."""

from ..dsl import variante

KATEGORIE = "Vorzeichen-Varianten"

SYSTEME = [
    variante("EF04", "VA01", faser="oben"),
    variante("KA01", "VA02", faser="oben"),
    variante("EF02", "VA03", x1="links"),
]
