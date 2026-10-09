import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import pipeline  # noqa: E402  (precisa do .env carregado antes)

# Evita acentos quebrados no console do Windows
sys.stdout.reconfigure(encoding="utf-8")


def main():
    pdf = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("matricula.pdf")
    if not pdf.exists():
        print(f"Arquivo não encontrado: {pdf}")
        sys.exit(1)

    print("=" * 50)
    print("  Pipeline de Avaliação Imobiliária")
    print(f"  Matrícula: {pdf.name}")
    print("=" * 50 + "\n")

    caminho_laudo = pipeline.executar(pdf)

    print(f"Laudo salvo em: {caminho_laudo.resolve()}\n")
    print("=" * 50)
    print(caminho_laudo.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
