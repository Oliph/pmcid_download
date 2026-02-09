# Import libraries
import concurrent.futures
import threading
import requests
from lxml import etree
import sqlite3
import sys
import os
import yaml
import logging
import random
import json
from tqdm import tqdm
import time
import urllib3.exceptions
from utils.retrieve_data_from_xml import DynamicXmlParser
from utils.record_data_to_db import create_tables, commit_to_database, analyze_database

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

logger = logging.getLogger(
    __name__
)  ## Supposed to be a global logger to work in concurrent.futures
logging.basicConfig(level=logging.INFO)


config_path = os.path.join(os.path.dirname(__file__), "../config", "config.yaml")
config_all = yaml.safe_load(open(config_path))


class MaxRetriesExceeded(Exception):
    def __init__(self, pmcid, max_retries):
        self.pmcid = pmcid
        self.max_retries = max_retries
        super().__init__(f"Max retries ({max_retries}) reached for pmcid {pmcid}")


def retry(max_retries=5, initial_delay=1):
    def decorator(func):
        def wrapper(*args, **kwargs):
            retries = 0
            retry_delay = initial_delay

            while retries < max_retries:
                try:
                    result = func(*args, **kwargs)
                    return result
                except (
                    urllib3.exceptions.MaxRetryError,
                    urllib3.exceptions.SSLError,
                ) as e:
                    retries += 1
                    if retries < max_retries:
                        # Retry with an increased delay
                        retry_delay *= 2
                        logger.info(f"Pause the API call, retry in {retry_delay}")
                        time.sleep(retry_delay)
                    else:
                        # Max retries reached, log the error and return None or raise an exception
                        logger.error(
                            f"Max retries ({max_retries}) reached. Unable to search PMC. Error: {e}"
                        )
                        raise MaxRetriesExceeded(args[0], max_retries)

        return wrapper

    return decorator


def get_xml(pmcid, path_folder, from_files=False):
    if from_files == "api":
        return api_search(pmcid)
    elif from_files == "files":
        return file_search(pmcid, path_folder)
    else:
        raise Exception(
            "xml_origin needs to be either 'api' or 'files, it is {from_files} right now"
        )


def file_search(pmcid, path_folder):
    xml_filename = f"{pmcid}.xml"
    full_path = os.path.join(path_folder, xml_filename)
    with open(full_path, "r") as f:
        xml_content = f.read()
        return pmcid, 200, xml_content


@retry(max_retries=5, initial_delay=1)
def api_search(pmcid):
    req = f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
    r = requests.get(req)
    try:
        if r.status_code == 200:
            return pmcid, 200, r.content
        else:
            logger.info(f"{pmcid}, {r.status_code}, {r.text}")
            return pmcid, r.status_code, None
    except TypeError:
        return pmcid, r.status_code, None


def getting_pmcids(xml_origin, pmcids_file_list, path_xml, conn, table_status, limit):
    def get_list_humans(file_location):
        """
        Get the list of pmcids from a list file
        """
        try:
            with open(file_location, "r") as f:
                for l in f:
                    yield l.split(",")[0].rstrip()
        except FileNotFoundError:
            raise

    def get_pmcids_in_folder(folder_path):
        """
        Get the already recorded pmcids from a folder
        """
        pmcids = []

        for filename in os.listdir(folder_path):
            if filename.endswith(".xml"):
                pmcid = os.path.splitext(filename)[0]
                pmcids.append(pmcid)

        return pmcids

    def get_pmcids_in_db(conn, table_status):
        """
        Get the already recorded pmcids from db
        """
        c = conn.cursor()
        # Execute a SELECT query to retrieve the pmcid values
        sql_query = f'SELECT pmcid FROM "{table_status}"'
        c.execute(sql_query)

        # Fetch all the pmcid values and store them in a list
        pmcid_list = [row[0] for row in c.fetchall()]
        c.close()
        return pmcid_list

    if xml_origin == "api":
        logger.info("Getting the list from db")
        original_list = list(get_list_humans(pmcids_file_list))
    elif xml_origin == "files":
        logger.info("Getting the list from files")
        original_list = get_pmcids_in_folder(path_xml)

    else:
        raise Exception("Need to be either 'file' with db path or 'api'")

    parsed_pmcids = get_pmcids_in_db(conn, table_status=table_status)
    ids_to_dl = list(set(original_list).difference(set(parsed_pmcids)))
    logger.info(f"Len of complete list of human pmcid: {len(original_list)}")
    logger.info(f"Len of already done species: {len(parsed_pmcids)}")
    random.shuffle(ids_to_dl)
    if limit and limit < len(ids_to_dl):
        ids_to_dl = ids_to_dl[0:limit]

    logger.info(f"Len of pmcid to parse: {len(ids_to_dl)}")
    return ids_to_dl


def write_file(xml_file, pmcid, path, record_file):
    # Write the XML string to a file
    if record_file:
        xml_filename = f"{pmcid}.xml"
        full_path = os.path.join(path, xml_filename)
        with open(full_path, "wb") as f:
            f.write(xml_file)
        f.close()  # FIXME should not be needed but crash with OSError: [Errno 24] Too many files, still don't know why
        return True
    else:
        return False


def processing_response(
    pmcid,
    api_response,
    response,
    folder_path,
    record_file,
    xml_origin
):
    status = {}
    sections = {}
    metadata = {}
    status["api_response"] = api_response
    if api_response == 200:
        xml_data = DynamicXmlParser(response)
        # Check if the article-type attribute exists
        # try:
        status["article_type"] = xml_data.data["article_type"]
        # except KeyError:  # Means an empty document
            # status['article_type'] = 'Empty document'

        if xml_origin == "files": 
            check_file = True
        if status["article_type"] == "research-article":
            # logger.info(f"{pmcid}: {xml_data.data_status}")
            # Only process the research-article type and the others record them in the
            # corresponding table to have track of the amount of different types
            # Record file in case the parser is not great and we need to
            # Check again. Should be removed as soon we are sure for the data we want.
            if record_file is True:
                check_file = write_file(
                    xml_file=response,
                    pmcid=pmcid,
                    path=folder_path,
                    record_file=record_file,
                )
            else:
                check_file = 'Not recording'

            # update the status dictionary
            # print(xml_data.data_status)
            try:
                del xml_data.data_status['article_type']
            except (KeyError, TypeError):
                pass
            status.update(xml_data.data_status)
            # Record if the xml has been recorded in file or not
            status["recorded_file"] = check_file
            # Creat the sections dictionary
            try:
                sections.update(xml_data.data["sections"])
            except (KeyError, TypeError):
                pass
            # Choose to put the abstract in section as it is long text
            try:
                sections["abstract"] = xml_data.data["abstract"]
            except (KeyError, TypeError):
                pass
            for k in ["sections", "article_type", "abstract"]:
                try:
                    del xml_data.data[k]
                except (KeyError, TypeError):
                    pass
            metadata.update(xml_data.data)
    # Return three dictionaries, the sections the metadata and the status of the collection
    # To record in three different tables later on
    return status, sections, metadata


def main():
    pmcid_human_file = config_all["api_europepmc_params"]["pmcid_human_file"]
    # # Name of the database
    DB_FILE = config_all["api_europepmc_params"]["db_info_articles"]
    record_file = config_all["api_europepmc_params"]["record_files"]
    path_xml = config_all["api_europepmc_params"]["article_human_folder"]
    if not os.path.exists(path_xml):
        os.makedirs(path_xml)
    xml_origin = config_all["api_europepmc_params"]["xml_origin"]
    if xml_origin == "files":
        record_file = False

    # FIXME: Move these variables in config file or in a class data
    table_status = "status"
    table_sections = "sections"
    table_metadata = "article_metadata"
    logging.info(f'Getting the files from: {path_xml}')
    # Connect to the db and ensure the table exists

    conn = sqlite3.connect(DB_FILE)
    create_tables(
        conn,
        table_sections=table_sections,
        table_status=table_status,
        table_metadata=table_metadata,
    )

    ids_to_dl = getting_pmcids(
        xml_origin=xml_origin,
        pmcids_file_list=pmcid_human_file,
        path_xml=path_xml,
        conn=conn,
        table_status=table_status,
        limit=None,
    )
    try:
        futures = []
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=20)
        logging.info("Getting the information from the list of pmcid")
        futures = [
            executor.submit(get_xml, pmcid, path_xml, xml_origin) for pmcid in ids_to_dl
        ]

        logger.info("Process started. Getting results")
        pbar = tqdm(total=len(ids_to_dl))  # Init pbar
        for future in concurrent.futures.as_completed(futures):
            pmcid, api_response, response = future.result()
            status, sections, metadata = processing_response(
                pmcid=pmcid,
                api_response=api_response,
                response=response,
                folder_path=path_xml,
                record_file=record_file,
                xml_origin=xml_origin
            )
            # Update the different tables
            for table, data in [
                (table_status, status),
                (table_sections, sections),
                (table_metadata, metadata),
            ]:
                if data:
                    commit_to_database(conn, pmcid, table, data)
            pbar.update(n=1)
            exception = future.exception()
            if exception:
                logger.error(
                    "Got an exception: {exception}.\nClose the db connection and exit."
                )
                raise (exception)

    except Exception as e:
        logger.error(f"An unexpected exception occurred: {e}. \nLast PMCID: {pmcid}")
        raise e  # Re-raise the exception for further handling if needed
    finally:
        try:
            status_results = analyze_database(conn, table_status)
            for k in status_results:
                try:
                    logger.info(f"{k}: \n\t\tTotal: {status_results[k]['recorded']} - Proportion: {status_results[k]['proportion']}")
                except KeyError:  # for the api_results
                   api_response = status_results['distinct_api_response']
                   
                   logger.info(f'API response code:')
                   for k in api_response:
                       logger.info(f"\t\t{k}: Total: {api_response[k]}")
        # Added when rerun to do some test without the full db
        except sqlite3.OperationalError:
            pass

        executor.shutdown()


if __name__ == "__main__":
    main()
