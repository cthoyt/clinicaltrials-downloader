"""Command line interface for :mod:`clinicaltrials_downloader`."""

import click

__all__ = [
    "main",
]


@click.command()
@click.option("--force", is_flag=True, help="Force re-download")
def main(force: bool) -> None:
    """Download the ClinicalTrials.gov data."""
    from .api import get_studies

    get_studies(force=force)


if __name__ == "__main__":
    main()
