from datetime import datetime
import re
from lxml import etree
from utils.relevant_tags import value_sections


class XmlParser:
    def __init__(self, xml_document):
        if isinstance(xml_document, str) or isinstance(xml_document, bytes):
            # Parse the XML string into an Element object
            # try:
            self.xml_document = etree.fromstring(xml_document)
            # except etree.XMLSyntaxError:
            # self.xml_document = None
            # raise Exception
        else:
            # If it's already an Element object, use it directly
            self.xml_document = xml_document

    @staticmethod
    def _extract_text_without_tags(element):
        if element is not None:
            text_iterator = element.itertext()
            # Go through all the tags and get the text. Add a space between them
            text = " ".join(text_iterator)
            # Remove all extra space after
            text = re.sub(r"\s+", " ", text).strip()
            return text

    def abstract(self):
        # Try to find the abstract element with sections
        xpath_expression_with_sec = ".//abstract/sec"
        # If no abstracts with sections are found, try to find abstracts without sections
        xpath_expression_no_sec = ".//abstract"
        # If no abstracts with sections are found, try to find abstracts without sections
        xpath_expression_p = ".//abstract/p"

        for xpath_expression in [
            xpath_expression_with_sec,
            xpath_expression_no_sec,
            xpath_expression_p,
        ]:
            abstract_elements = self.xml_document.findall(xpath_expression)
            abstract_elements = [
                el.text for el in abstract_elements if el.text is not None
            ]
            if abstract_elements:
                # If abstracts with sections are found, concatenate their text
                abstract_text = " ".join(
                    abstract_element.strip() for abstract_element in abstract_elements
                )
                if abstract_text.strip():
                    return abstract_text

    def article_type(self):
        article_type = self.xml_document.get("article-type")
        if article_type:
            return article_type

    def article_title(self):
        title_xpath = ".//article-title"
        title_element = self.xml_document.find(title_xpath)
        title = XmlParser._extract_text_without_tags(title_element)
        if title:
            return title

    def authors(self):
        author_xpath = ".//contrib[@contrib-type='author']"
        author_elements = self.xml_document.findall(author_xpath)
        authors = []
        for author_element in author_elements:
            name_element = author_element.find("name")
            if name_element is not None:
                surname = name_element.findtext("surname")
                given_names = name_element.findtext("given-names")
                authors.append(f"{given_names} {surname}")
        if authors:
            return authors

    def article_categories(self):
        categories_xpath = ".//article-categories/subj-group/subject"
        categories_elements = self.xml_document.findall(categories_xpath)
        categories = [
            XmlParser._extract_text_without_tags(el) for el in categories_elements
        ]
        if categories:
            return categories

    def journal_title(self):
        journal_title_xpath = ".//journal-title"
        journal_title_element = self.xml_document.find(journal_title_xpath)
        journal_title = XmlParser._extract_text_without_tags(journal_title_element)
        if journal_title:
            return journal_title

    def publication_date(self):
        # FIXME change that one to match the publication date not the other one
        pub_date_xpath = ".//pub-date"
        pub_date_element = self.xml_document.find(pub_date_xpath)
        if pub_date_element is not None:
            year = pub_date_element.findtext("year")
            month = pub_date_element.findtext("month")
            day = pub_date_element.findtext("day")
            if year and month and day:
                # Convert year, month, and day to integers
                year = int(year)
                month = int(month)
                day = int(day)
                # Create a datetime object
                publication_date = datetime(year, month, day)

                return publication_date

    def copyright_info(self):
        copyright_xpath = ".//permissions/copyright-statement"
        copyright_element = self.xml_document.find(copyright_xpath)
        copyright_ = XmlParser._extract_text_without_tags(copyright_element)
        if copyright_:
            return copyright_

    def keywords(self):
        kwd_xpath = ".//kwd-group/kwd"
        kwd_elements = self.xml_document.findall(kwd_xpath)
        if kwd_elements is not None:
            return [XmlParser._extract_text_without_tags(el) for el in kwd_elements]

    def ids(self):
        dict_ids = dict()
        pmcid_xpath = ".//article-id[@pub-id-type='pmcid']"
        publisher_id_xpath = ".//article-id[@pub-id-type='publisher-id']"
        doi_xpath = ".//article-id[@pub-id-type='doi']"
        pmcid_element = self.xml_document.find(pmcid_xpath)
        publisher_id_element = self.xml_document.find(publisher_id_xpath)
        doi_element = self.xml_document.find(doi_xpath)

        pmcid_text = XmlParser._extract_text_without_tags(pmcid_element)
        if pmcid_text:
            dict_ids["pmcid"] = pmcid_text
        else:
            dict_ids["pmcid"] = None

        publisher_id_text = XmlParser._extract_text_without_tags(publisher_id_element)
        if publisher_id_text:
            dict_ids["publisher_id"] = publisher_id_text
        else:
            dict_ids["publisher_id"] = None

        doi_text = XmlParser._extract_text_without_tags(doi_element)
        if doi_text:
            dict_ids["doi"] = doi_text
        else:
            dict_ids["doi"] = None
        return dict_ids

    def funding(self):
        funding_xpath = ".//funding-source"
        funding_elements = self.xml_document.findall(funding_xpath)
        funding_info = []

        for funding_element in funding_elements:
            for element, key in [
                (".//institution", "institution"),
                (".//award_id", "award_id"),
                (
                    ".//principal-award-recipient/name",
                    "recipient_name",
                ),
            ]:
                funding_dict = {}
                try:
                    funding_el = funding_element.find(element)
                    funding_text = XmlParser._extract_text_without_tags(funding_el)
                    if funding_text:
                        funding_dict[key] = funding_text
                        funding_info.append(funding_dict)
                except AttributeError:
                    pass
        if funding_info:
            return funding_info

    def sections(self):
        dict_section = {k: None for k in value_sections}
        sections_xpath = ".//body/sec"
        sec_elements = self.xml_document.findall(sections_xpath)
        # Iterate through the sec elements
        for sec in sec_elements:
            sec_type = sec.attrib.get("sec-type", "").lower()
            # Check if the sec-type attribute matches any of the section fields
            for section in value_sections:
                for value in value_sections[section]:
                    if value in sec_type:
                        section_text = XmlParser._extract_text_without_tags(sec)
                        dict_section[section] = section_text
        if any(value is not None for value in dict_section.values()):
            return dict_section
        return dict_section


class DynamicXmlParser(XmlParser):
    """
    A class for dynamically parsing XML documents, building on the functionality provided by XmlParser.

    This class extends the XmlParser class and is designed to perform dynamic XML parsing,
    where various methods are automatically called to extract data from the XML document.
    The results are stored in a dictionary, and the status of each method is recorded
    to determine if the extraction was successful.

    Attributes:
        data (dict): A dictionary to store the results of various extraction methods.
        data_status (dict): A dictionary to store the status of each method,
        indicating whether it succeeded or not.

    Methods:
        _get_the_parents_methods: Internal method to retrieve the methods from the parent class (XmlParser).
        _collect_results: Internal method to call each method and store the results in the data dictionary.
        _check_methods: Internal method to check the status of each method and populate the data_status dictionary.

    Example Usage:
        # Create a DynamicXmlParser instance with an XML document
        parser = DynamicXmlParser(xml_document)

        # Access the extracted data and its status
        data = parser.data
        status = parser.data_status
    """

    def __init__(self, xml_document):
        self.data = {}  # Initialize a dictionary to store method results
        self.data_status = {}  # Initialize a dict to store the method status
        super().__init__(xml_document)
        # Get the parents methods
        self._get_the_parents_methods()
        # Collect the results
        self._collect_results()
        # Populate the checking status
        self._check_methods()

    def _get_the_parents_methods(self):
        """
        Retrieves the methods from the parent class, XmlParser.
        """
        self.parent_class_methods = [
            func
            for func in dir(XmlParser)
            if callable(getattr(XmlParser, func)) and not func.startswith("_")
        ]

    def _collect_results(self):
        """
        Calls the methods and stores the results in the data dictionary.
        """
        try:
            # Call each method and store the result in the data dictionary
            for method_name in self.parent_class_methods:
                method = getattr(self, method_name)
                try:
                    result = method()
                except Exception as e:
                    raise ValueError(
                        f"Method {method_name} failed with error: {str(e)}"
                    )
                self.data[method_name] = result
        except Exception as e:
            raise e

    def _check_methods(self):
        """
        Checks the status of each method's execution and populates the data_status dictionary.
        """
        for method_name in self.data:
            result = self.data[method_name]
            if result is None or (isinstance(result, (str, list)) and not result):
                self.data_status[method_name] = False
            else:
                if isinstance(result, dict):
                    for k in result:
                        if result[k] is not None:
                            self.data_status[k] = True
                        else:
                            self.data_status[k] = False
                    # To avoid having the parent key recorded
                    del result
                else:
                    self.data_status[method_name] = True
