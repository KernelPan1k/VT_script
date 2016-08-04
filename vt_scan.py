#!/usr/bin/env python
# -*- coding: utf-8 -*-

from json import loads
from urllib import urlencode
from urllib2 import Request, urlopen, HTTPError, URLError
from time import sleep
from re import search
from os import system, remove
from optparse import OptionParser

parser = OptionParser("usage: %prog -f path_to_file [options]")
parser.add_option("-f", "--file",
                  help="file to use",
                  action="store", default=None,
                  dest="path_to_file")
parser.add_option("-k", "--key",
                  help="use to set your VT api key",
                  action="store", default='',
                  dest="apikey")

(options, args) = parser.parse_args()


def get_file_type(first_line):
    "Search on the first_line to find some keyword helping identifying the file type"
    if "ZHPDiag" in first_line:
        return "ZHPDiag"
    if "OTL" in first_line:
        return "OTL"
    if "FRST" in first_line:
        return "FRST"
    return "RAW"


def search_on_vt(md5s, apikey):
    "Create a VT API request and return the answer"
    url = "https://www.virustotal.com/vtapi/v2/file/report"
    parameters = {"resource": md5s, "apikey": apikey}
    data = urlencode(parameters)
    req = Request(url, data)
    response = urlopen(req)
    return loads(response.read())


def run_vt_analyse(md5s_list, apikey):
    # Format the md5s_list for the request
    md5_request = ""
    for md5 in md5s_list:
        md5_request = md5_request + md5[0] + ", "
    md5_request = md5_request[:-2]

    # Get the request answer
    answer_list = None
    while answer_list is None:
        try:
            answer_list = search_on_vt(md5_request, apikey)
        except ValueError:
            answer_list = None
            output("### Error, VT refuse to answer, the script will retry in 30sec.")
            sleep(30)
        except HTTPError:
            output("Your apikey %s seem to be refuse by VirusTotal." % apikey)
            exit()
        except URLError:
            output("You should check your internet connexion")
            exit()

    # Analyse the answer
    if len(md5s_list) == 1:
        analyse_answer(answer_list, md5s_list)
    else:
        for answer in answer_list:
            analyse_answer(answer, md5s_list)


def analyse_answer(answer, md5s_list):
    # Check if VT have found the associate the file
    if answer.get("response_code", 0) == 0:
        md5 = answer.get("resource", "error")
        filename = get_filename_for_md5(md5, md5s_list)
        output("VirusTotal seems to not know file: %s with md5:%s." % (filename, md5))

    else:
        # output answer
        md5 = answer.get(u"md5", None).lower()
        filename = get_filename_for_md5(md5, md5s_list)
        positives = answer.get("positives", None)
        total = answer.get("total", None)
        url = "https://www.virustotal.com/latest-scan/" + md5
        output("%s/%s for %s, more info at %s" % (positives, total, filename, url))


def get_filename_for_md5(md5, md5s_list):
    "Find the associate filename to a md5"
    for element in md5s_list:
        if element[0].lower() == md5.lower():
            return element[1]
    raise ValueError


def find_md5_in_file(path_to_file):
    "Find all md5 and the name of the associated file"
    md5s_dict = {}
    md5s_list = []
    with open(path_to_file, 'r') as f:
        for line in f:

            # Parse the line to find if there is a 32 hex number
            search_md5 = search('(' + r'[0-9a-fA-F]' * 32 + ')', line)
            if not search_md5:
                continue
            md5 = search_md5.group(0)

            # Little hack to exclude CLSIDs
            md5_index = line.index(md5)
            if md5_index > 0 and line[md5_index - 1] == "{":
                continue

            md5 = md5.lower()

            if md5s_dict.get(md5, False):
                # We doesn't want to search multiples times for the same md5
                continue
            md5s_dict[md5] = True

            # Parse the line to find if there is a filename with format (roughly) \anything.anything
            search_filename = search(r'\\([\w\-\s]+\.\w+)', line)
            if search_filename:
                md5s_list.append((md5, search_filename.group(0)[1:]))
            else:
                md5s_list.append((md5, "'no filename'"))

    return md5s_list

def output(message):
    system("echo %s >> output.txt" % message)
    print(message)


def run(options):

    if not options.path_to_file:
        try:
            with open("input.txt", 'r') as f:
                if f.readline():
                    options.path_to_file = "input.txt"
        except IOError:
            output('you must use an input file, save it as input.txt or use -f option in command line')
            parser.error('you must use an input file, save it as input.txt or use -f option in command line')


    if not options.apikey:
        try:
            with open("apikey.txt", 'r') as f:
                apikey = f.readline().replace("\n", "").replace(" ", "").replace("\r", "")
            if not apikey:
                output('you must use an apikey, set it in apikey.txt or use -k option in command line')
                parser.error('you must use an apikey, set it in apikey.txt or use -k option in command line')
        except IOError:
            output('you must use an apikey, set it in apikey.txt or use -k option in command line')
            parser.error('you must use an apikey, set it in apikey.txt or use -k option in command line')
    else:
        # We want to use by default the apikey from command line
        apikey = options.apikey

    # Remove the old output file
    remove("output.txt")

    # Tell the user which API key will be used
    output("The script will use VT API key: '%s'" % apikey)

    # Detect the logFile type
    with open(options.path_to_file, 'r') as f:
        file_type = get_file_type(f.readline())
        output("The input file is detected as a %s log." % file_type)

    # Find the md5s in the file
    md5s_list = find_md5_in_file(options.path_to_file)
    if len(md5s_list) == 0:
        output(
          "Found 0 md5 in %s, if there is md5, convert the log file encoding to 'utf-8'."
          % options.path_to_file
        )
        exit()
    output("Found %s different md5s in %s." % (len(md5s_list), options.path_to_file))
    output("The analysis should take about %s min." % int(len(md5s_list) / 16 + 1))

    # Search on VT for each md5 by group of 4
    while len(md5s_list) >= 4:
        run_vt_analyse(md5s_list[0:4], apikey)
        md5s_list = md5s_list[4:]

        # The VirusTotal public API allow 4 request each minute,
        # therefore we should wait 15sec between each request.
        sleep(15)
    run_vt_analyse(md5s_list, apikey)

    output("### End of analysis.")

run(options)
