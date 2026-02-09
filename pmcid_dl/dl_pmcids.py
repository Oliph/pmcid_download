import requests
from requests.exceptions import HTTPError

import concurrent.futures
import random
import gzip
import io
import logging
import os
import yaml
import sys
from tqdm import tqdm
import urllib.parse

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
logging.basicConfig(level = logging.INFO)
logger = logging.getLogger(__name__)


config_path = os.path.join(os.path.dirname(__file__), "../config", "config.yaml")
config_all = yaml.safe_load(open(config_path))


def get_request(url, payload):
    params = urllib.parse.urlencode(payload, quote_via=urllib.parse.quote)
    try:
        response = requests.get(url, params)
        # If the response was successful, no Exception will be raised
        response.raise_for_status()
    except HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
    except Exception as err:
        print(f"Other error occurred: {err}")
    else:
        return response


def get_archive(file_location, url, rerun=False):
    if rerun is False:
        try:
            open_f = open(file_location, "rb")
            f = io.BytesIO(open_f.read())
        except FileNotFoundError:
            rerun = True
    if rerun is True:
        logger.info(f"Getting the archive at {url}")

        OAUrl = requests.get(url)
        gzFile = OAUrl.content
        location = open(file_location, "wb")
        location.write(gzFile)
        f = io.BytesIO(gzFile)
        logger.info(f"Writing archive in {file_location}")
    with gzip.GzipFile(fileobj=f) as OAFiles:
        for OAFile in OAFiles:
            yield str(OAFile[:-1], "utf-8")


def get_species(pmcid, annotation_url):
    url = annotation_url
    pmcid_to_load = f"PMC:{pmcid[3:]}"
    payload = {
        "articleIds": pmcid_to_load,
        "type": "Organisms",
        "section": "Methods",
        "provider": "Europe PMC",
        # 'provider': requests.utils.quote('Europe PMC'),
        "format": "JSON",
    }
    result = get_request(url, payload)
    try:
        result_json = result.json()
        species = set()
        for dictionary in result_json:
            for d in dictionary["annotations"]:
                species.add(d["exact"])

        return pmcid, species

    except AttributeError:  # When not getting anything
        pass


def get_parsed_list_species(file_location):
    try:
        with open(file_location, "r") as f:
            for l in f:
                yield l.split(",")[0].rstrip()
    except FileNotFoundError:
        pass


def get_list_to_dl(list_pmcids, pmcid_species_location):
    logger.info(f"Len of pmcid_to_dl: {len(list_pmcids)}")

    list_parsed_species = set(get_parsed_list_species(pmcid_species_location))
    logger.info(f"Len of already done species: {len(list_parsed_species)}")

    ids_to_dl = list(set(list_pmcids).difference(list_parsed_species))
    logger.info(f"Len of pmcid to parse: {len(ids_to_dl)}")
    # Randomize the list to avoid downloading only the first articles
    random.shuffle(ids_to_dl)
    return ids_to_dl


def check_species(specie_list, human_terms):
    if any(x in human_terms for x in specie_list):
        return True


def main():
    rerun_archive = config_all["search_params"]["rerun_archive"]
    human_terms = config_all["search_params"]["human_terms"]

    archive_url = config_all["api_europepmc_params"]["archive_api"]["root_url"]
    annotation_api = config_all["api_europepmc_params"]["annotations_api"]["root_url"]

    archive_file = config_all["api_europepmc_params"]["archive_file"]
    pmcid_species_file = config_all["api_europepmc_params"]["pmcid_species_file"]
    pmcid_human_file = config_all["api_europepmc_params"]["pmcid_human_file"]

    logger.info("Downloading archive")
    list_pmcids = list(get_archive(archive_file, archive_url, rerun_archive))

    logger.info(f"Got the list of pmcids: {len(list_pmcids)}")
    ids_to_dl = get_list_to_dl(list_pmcids, pmcid_species_file)

    futures = []
    executor = concurrent.futures.ThreadPoolExecutor()
    logging.info("Getting the species from the list of pmcid")
    futures = [
        executor.submit(get_species, pmcid, annotation_api) for pmcid in ids_to_dl
    ]

    print("Process started. Getting results")
    pbar = tqdm(total=len(ids_to_dl))  # Init pbar
    with open(pmcid_species_file, "a") as f:
        for future in concurrent.futures.as_completed(futures):
            result_pmcid, species = future.result()

            f.write(f"{result_pmcid},{','.join(species)}")
            f.write("\n")
            if check_species(species, human_terms) is True:
                with open(pmcid_human_file, "a") as f_h:
                    f_h.write(f"{result_pmcid}")
                    f_h.write("\n")

            pbar.update(n=1)
            exception = future.exception()
            if exception:
                raise (exception)


if __name__ == "__main__":
    main()
