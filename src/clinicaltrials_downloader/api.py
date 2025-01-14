"""Download ClinicalTrials.gov."""

from __future__ import annotations

import gzip
import json
import logging
import time
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, TypeAlias, cast

import pystow
import requests
from tqdm import tqdm

if TYPE_CHECKING:
    import zenodo_client

__all__ = [
    "get_studies",
    "iterate_download_studies",
    "upload_zenodo",
]

logger = logging.getLogger(__name__)

# See field name list at
# https://clinicaltrials.gov/data-api/about-api/study-data-structure
DEFAULT_FIELDS = [
    # "protocolSelection.identificationModule.nctId",
    "NCTId",
    "BriefTitle",
    # "protocolSelection.identificationModule.briefTitle",
]

SLIM_FIELDS = [
    "NCTId",
    "BriefTitle",
    "Condition",
    "ConditionMeshTerm",  # ConditionMeshTerm is the name of the disease
    "ConditionMeshId",
    "InterventionName",  # InterventionName is the name of the drug/vaccine
    "InterventionType",
    "InterventionMeshTerm",
    "InterventionMeshId",
    "StudyType",
    "DesignAllocation",
    "OverallStatus",
    "Phase",
    "WhyStopped",
    "SecondaryIdType",
    "SecondaryId",
    "StartDate",  # Month [day], year: "November 1, 2023", "May 1984" or NaN
    "StartDateType",  # "Actual" or "Anticipated" (or NaN)
    "ReferencePMID",  # these are tagged as relevant by the author, but not necessarily about the trial
]

#: The API endpoint for studies
STUDIES_ENDPOINT_URL = "https://clinicaltrials.gov/api/v2/studies"

MODULE = pystow.module("bio", "clinicaltrials")

PATH = MODULE.join(name="results.json.gz")
PATH_SAMPLE = MODULE.join(name="results_sample.json")

#: This is the maximum page size allowed by the API
MAXIMUM_PAGE_SIZE = 1000

#: The number of studies to save in the sample file
N_SAMPLE_ROWS = 5

#: A type annotation representing a raw study
RawStudy: TypeAlias = dict[str, Any]


def get_studies(*, force: bool = False) -> list[RawStudy]:
    """Get the full ClinicalTrials.gov data dump.

    :param force: Should the data be re-downloaded (and the cache invalidated?)
    :return:
        A list of raw dictionaries representing studies in ClinicalTrials.gov,
        as they are returned by the `ClinicalTrials.gov API <https://clinicaltrials.gov/data-api/api>`_

    In January 2025, this took a bit less than 10 minutes to download 522K
    studies with a decent internet connection. It weights about 2GB gzipped.

    .. warning::

        The results are cached to :data:`PATH`. You should
        periodically set force=True to re-download the database,
        since new records are added on a daily basis.

        Order is not guaranteed, so, unfortunately, this can't
        be done incrementally.

    If you want more control over how downloading works, see
    :func:`iterate_download_studies`.
    """
    if PATH.exists() and not force:
        with gzip.open(PATH, "rt") as file:
            t = time.time()
            logger.info("loading cached ClinicalTrials.gov")
            rv = cast(list[RawStudy], json.load(file))
            logger.info("loaded cached ClinicalTrials.gov in %f seconds", time.time() - t)
            return rv

    studies = list(iterate_download_studies(page_size=MAXIMUM_PAGE_SIZE))

    with PATH_SAMPLE.open("w") as file:
        json.dump(studies[:N_SAMPLE_ROWS], file, indent=2)

    with gzip.open(PATH, "wt") as file:
        json.dump(studies, file)

    return studies


def iterate_download_studies(
    *,
    page_size: int | None = None,
    fields: list[str] | None = None,
) -> Iterable[RawStudy]:
    """Download studies iteratively by paging through the ClinicalTrials.gov API.

    :param page_size: The page size when hitting the API
    :param fields:
        the fields to download. See a full list at
        https://clinicaltrials.gov/data-api/about-api/study-data-structure.
        For example, a small field list of ``["NCTId", "BriefTitle"]`` is useful
        for quickly checking the database.
    :yields: Individual dictionaries corresponding to studies

    .. seealso:: `ClinicalTrials.gov API documentation <https://clinicaltrials.gov/data-api/api>`_
    """
    if page_size is None:
        page_size = MAXIMUM_PAGE_SIZE

    if page_size > MAXIMUM_PAGE_SIZE:
        page_size = MAXIMUM_PAGE_SIZE

    parameters: dict[str, str | int] = {
        "pageSize": page_size,
    }
    if fields is not None:
        parameters["fields"] = ",".join(DEFAULT_FIELDS)

    # on the first get, we need to return the count so we can make a progress bar
    # note that countTotal needs to be encoded with a string, and not a proper boolean
    res = requests.get(
        STUDIES_ENDPOINT_URL, params={**parameters, "countTotal": "true"}, timeout=5
    ).json()

    total = res["totalCount"]
    yield from res["studies"]

    with tqdm(
        desc="Downloading ClinicalTrials.gov",
        total=total,
        unit="trial",
        unit_scale=True,
    ) as pbar:
        # update the progress bar based on the initial result
        # size
        pbar.update(page_size)

        # While there's a nextPageToken field available in the result,
        # get a new page. We don't need the countTotal anymore. Make
        # sure to overwrite the original variable name each time.
        while next_token := res.get("nextPageToken"):
            res = requests.get(
                STUDIES_ENDPOINT_URL,
                params={**parameters, "pageToken": next_token},
                timeout=5,
            ).json()
            studies = res["studies"]
            yield from studies
            pbar.update(len(studies))


def upload_zenodo(client: zenodo_client.Client | None = None) -> None:
    """Re-process and upload the current data to Zenodo."""
    if client is None:
        from zenodo_client import Client

        client = Client()

    get_studies(force=True)
    raise NotImplementedError
