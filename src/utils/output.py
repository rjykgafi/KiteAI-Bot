import os
from rich.console import Console
from rich.text import Text
from tabulate import tabulate
from rich.table import Table
from rich import box


def show_logo():
    """Отображает стильный логотип"""
    # Очищаем экран
    os.system("cls" if os.name == "nt" else "clear")

    console = Console()

    # Создаем звездное небо со стилизованным логотипом
    logo_text = """"""

    # Создаем градиентный текст
    gradient_logo = Text(logo_text)
    gradient_logo.stylize("bold bright_cyan")

    # Выводим с отступами
    console.print(gradient_logo)
    print()


def show_dev_info():
    """Displays development and version information"""
    console = Console()

    # Создаем красивую таблицу
    table = Table(
        show_header=False,
        box=box.DOUBLE,
        border_style="bright_cyan",
        pad_edge=False,
        width=85,
        highlight=True,
    )

    # Добавляем колонки
    table.add_column("Content", style="bright_cyan", justify="center")

    # Добавляем строки с контактами
    table.add_row("✨ KiteAI Bot 1.0 ✨")
    table.add_row("─" * 43)
    table.add_row("")
    table.add_row("⚡ GitHub: [link]https://github.com/rjykgafi[/link]")
    table.add_row("")

    # Выводим таблицу с отступом
    print("   ", end="")
    print()
    console.print(table)
    print()
