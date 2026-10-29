class VersionNoEditable(Exception):
    """Se intentó cambiar el contenido de una versión que no está en BORRADOR."""


class RegistroNoBorrable(Exception):
    """Los registros del presupuesto no se borran: se anulan con motivo."""
