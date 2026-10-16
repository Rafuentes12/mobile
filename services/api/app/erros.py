class ErroNegocio(Exception):
    """Regra de negócio violada; vira uma resposta HTTP com `detail` legível."""

    def __init__(self, mensagem: str, status: int = 400) -> None:
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status = status
