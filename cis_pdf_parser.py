#!/usr/bin/env python3

import fitz
import csv
import re
import logging
import argparse
import sys
import unittest

def clean_pdf_text(text):
    # Normalize line endings
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    
    # Keep paragraph breaks (double newlines), remove single newlines inside paragraphs
    text = re.sub(r'(?<!\n)\n(?!\n)', ' ', text)

    # Optional: collapse multiple spaces
    text = re.sub(r' +', ' ', text)

    # Optional: trim leading/trailing whitespace
    return text.strip()

def main():
    defval = ""
    cis = ""
    
    # Initialize variables
    (
        rule_count,
        level_count,
        description_count,
        acnt,
        rat_count,
        rem_count,
        defval_count,
        cis_count,
    ) = (0,) * 8
    firstPage = None
    seenList = []

    # Setup console logging
    logger = logging.getLogger()
    logger.setLevel(logging.INFO) # Change to DEBUG, INFO, WARNING, ERROR, or CRITICAL

    if logger.hasHandlers():
        logger.handlers.clear()

    logging_streamhandler = logging.StreamHandler(stream=None)
    logging_streamhandler.setFormatter(
        logging.Formatter(fmt="%(asctime)s %(levelname)-8s %(message)s")
    )
    
    # Set handler's level to match (important!)
    logging_streamhandler.setLevel(logging.INFO) # Change to DEBUG, INFO, WARNING, ERROR, or CRITICAL
    
    logger.addHandler(logging_streamhandler)

    parser = argparse.ArgumentParser(
        description="Parses CIS Benchmark PDF content into CSV Format"
    )
    required = parser.add_argument_group("required arguments")
    required.add_argument(
        "-p", "--pdf_file", type=str, required=True, help="PDF File to parse"
    )
    required.add_argument(
        "-o", "--out_file", type=str, required=True, help="Output file in .csv format"
    )
    required.add_argument(
        '-l', '--log-level', type=str, required=False, help="Set log level (DEBUG, INFO, etc). Default to INFO",
        default="INFO"
    )
    args = parser.parse_args()

    log_level = getattr(logging, args.log_level.upper(), None)
    if not isinstance(log_level, int):
        logger.error(f"Invalid log level: {args.log_level}")
        sys.exit(1)

    try:
        logger.setLevel(log_level)
        logging_streamhandler.setLevel(log_level)
    except ValueError:
        logger.error("Invalid log level: {}. Valid log levels can be found here "
                      "https://docs.python.org/3/howto/logging.html".format(args.log_level))
        sys.exit(1)

    # Open PDF File
    doc = fitz.open(args.pdf_file)

    # Get CIS Type from the name of the document in the cover page as it doesn't appear in the metadata
    coverPageText = doc.load_page(0).get_text("text")
    logger.debug(coverPageText)
    try:
        pattern = "(?<=CIS).*(?=Benchmark)"
        rerule = re.search(pattern, coverPageText, re.DOTALL)
        if rerule is not None:
            CISName = rerule.group(0).strip().replace('\n','')
            logger.info("*** Document found name: {} ***".format(CISName))
            if "Red Hat Enterprise Linux 7" in CISName:
                pattern = "(\d+(?:\.\d.\d*)+)(.*?)(\(Automated\)|\(Manual\))"
            elif "Debian Linux 11" in CISName:
                pattern = "(\d+(?:\.\d.\d*)+)(.*?)(\(Automated\)|\(Manual\))"
            elif "Microsoft Windows Server 2019" in CISName:
                pattern = "(\d+(?:\.\d+)+)\s\(((L[12])|(NG))\)(.*?)(\(Automated\)|\(Manual\))"
            elif "Microsoft Windows 10 Enterprise" in CISName:
                pattern = "(\d+(?:\.\d+)+)\s\(((L[12])|(NG)|(BL))\)(.*?)(\(Automated\)|\(Manual\))"
            elif "Amazon Web Services Foundations" in CISName:
                pattern = "(\d+(?:\.\d.\d*)+)(.*?)(\(Automated\)|\(Manual\))"
            elif "Microsoft Azure Foundations" in CISName:
                pattern = "(\d+(?:\.\d.\d*)+)(.*?)(\(Automated\)|\(Manual\))"
            else:
                raise ValueError("Could not find a matching regex for {}".format(CISName))
    except IndexError:
        logger.error("*** Could not find CIS Name, exiting. ***")
        sys.exit(1)

    # Skip to actual rules
    for currentPage in range(len(doc)):
        findPage = doc.load_page(currentPage)
        # logger.debug("Page number : {}".format(currentPage.__index__()))
        # logger.debug(findPage.get_text())
        if findPage.search_for("Recommendations 1 "):
            firstPage = currentPage

    # If no "Recommendations" and "Initial Setup" it is not a full CIS Benchmark .pdf file
    if firstPage is None:
        logger.error("*** Not a CIS PDF Benchmark, exiting. ***")
        sys.exit(1)

    logger.info(f"*** Total Number of Pages: {doc.page_count} ***")

    # Open output .csv file for writing
    with open(args.out_file, mode="w") as cis_outfile:
        rule_writer = csv.writer(
            cis_outfile, delimiter=",", quotechar='"', quoting=csv.QUOTE_MINIMAL
        )
        rule_writer.writerow(
            [
                "Rule",
                "Profile Applicability",
                "Description",
                "Rationale",
                "Audit",
                "Remediation",
                "Default Value",
                "CIS Controls",
            ]
        )

        # Loop through all PDF pages
        for page in range(firstPage, len(doc)):
            if page < len(doc):
                data = doc.load_page(page).get_text("text")
                logger.info(f"*** Parsing Page Number: {page} ***")

                # Get rule by matching regex pattern for x.x.* (Automated) or (Manual), there are no "x.*" we care about
                try:
                    rerule = re.search(pattern, data, re.DOTALL)
                    if rerule is not None:
                        rule = rerule.group()
                        rule_count += 1
                except IndexError:
                    logger.debug(f"*** Page {page} does not contain a Rule Name ***")
                except AttributeError:
                    logger.debug(f"*** Page {page} does not contain a Rule Name ***")

                # Get Profile Applicability by splits as it is always between Profile App. and Description, faster than regex
                try:
                    l_post = data.split("Profile Applicability:", 1)[1]
                    level = l_post.partition("Description:")[0].strip()
                    level = re.sub("[^a-zA-Z0-9\\n-]+", " ", level)
                    level_count += 1
                except IndexError:
                    logger.debug(f"*** Page {page} does not contain Profile Levels ***")

                # Get Description by splits as it is always between Description and Rationale, faster than regex
                try:
                    d_post = data.split("Description:", 1)[1]
                    description = d_post.partition("Rationale")[0].strip()
                    description = clean_pdf_text(description)
                    description_count += 1
                except IndexError:
                    logger.debug(f"*** Page {page} does not contain Description ***")

                # Get Rationale by splits as it is always between Rationale and Audit, faster than regex
                try:
                    rat_post = data.split("Rationale:", 1)[1]
                    rat = rat_post.partition("Audit:")[0].strip()
                    rat = clean_pdf_text(rat)
                    rat_count += 1
                except IndexError:
                    logger.debug(f"*** Page {page} does not contain Rationale ***")

                # Get Audit by splits as it is always between Audit and Remediation, faster than regex
                try:
                    a_post = data.split("\nAudit:", 1)[1]
                    audit = a_post.partition("Remediation")[0].strip()
                    audit = clean_pdf_text(audit)
                    acnt += 1
                except IndexError:
                    logger.debug(f"*** Page {page} does not contain Audit ***")

                # Get Remediation by splits as it is always between Remediation and Default value, faster than regex
                try:
                    rem_post = data.split("Remediation:", 1)[1]
                    rem = rem_post.partition("Default Value:")[0].strip()
                    rem_count += 1
                except IndexError:
                    logger.debug(f"*** Page {page} does not contain Remediation ***")

                # Get Default Value by splits as WHEN PRESENT it is always between Default Value and CIS Controls,
                # Faster than regex
                # Found to be always present in Windows 2019 but NOT in RHEL 7
                try:
                    defval_post = data.split("Default Value:", 1)[1]
                    defval = defval_post.partition("CIS Controls:")[0].strip()
                    defval_count += 1
                except IndexError:
                    logger.debug(f"*** Page {page} does not contain Default Value ***")

                # Get CIS Controls by splits as they are always between CIS Controls and P a g e, regex the result
                try:
                    cis_post = data.split("CIS Controls:", 1)[1]
                    cis = cis_post.partition("P a g e")[0].strip()
                    cis = re.sub("[^a-zA-Z0-9\\n.-]+", " ", cis)
                    cis_count += 1
                    # Incrementing defval_count if cis_count is found as Default Value is not always present (ex: RHEL7)
                    if defval_count == (cis_count-1):
                        defval = ""
                        defval_count += 1
                except IndexError:
                    logger.debug(f"*** Page {page} does not contain CIS Controls ***")

                # We only write to csv if a parsed rule is fully assembled
                if rule_count:
                    row_count = [
                        rule_count,
                        level_count,
                        description_count,
                        rat_count,
                        acnt,
                        rem_count,
                        #defval_count,
                        #cis_count,
                    ]
                    logger.debug(row_count)
                    if row_count.count(row_count[0]) == len(row_count):
                        # Have we seen this rule before? If not, write it to file
                        if row_count not in seenList:
                            seenList = [row_count]
                            logger.debug("*** Writing the following rule to csv: ***")
                            row = [rule, level, description, rat, audit, rem, defval, cis]
                            logger.debug(row)
                            rule_writer.writerow(row)
                page += 1
            else:
                logger.info("*** All pages parsed, exiting. ***")
                sys.exit()


# Setup command line arguments
if __name__ == "__main__":
    main()
