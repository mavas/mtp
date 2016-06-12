"""
MTP protocol utilities.

Mainly is an interface to command-line tools.
"""


import re, os, sys
import shlex
from time import sleep
import subprocess
import logging

from django.conf import settings
from fabric.context_managers import settings as fabsettings
from fabric.context_managers import hide
from fabric.operations import sudo
from fabric.api import run, env


log = logging.getLogger('root')
env.hosts = ['localhost']


def parse_files2(s, filename):
    """
    Parses the output of mtp-files to produce a list of objects.
    """
    ret = list()
    found_filename = False
    found_filesize = False
    found_fileID = False
    # Loop.
    temp_fileID, temp_filename = None, None
    for line in s.split("\n"):
        # If this variable is set, it means the previous line was a file ID,
        # and so this line should be a filename; if this turns out ending up
        # not being the case, something went wrong.
        if found_fileID and not found_filename:
            m = re.match(r'^\s+Filename: (.+)$', line)
            if m and m.group(1) == filename:
                found_filename = True
                temp_filename = m.group(1)
                continue
        if found_fileID and found_filename:
            m = re.match(r'^\s+File size (\d+)\s+.+$', line)
            if m:
                file_size = int(m.group(1))
                new_val = (temp_fileID, temp_filename, file_size)
                ret.append(new_val)
                found_fileID = found_filename = False
                continue
        # Find the "File ID:" line.
        m = re.match(r'^File ID: (\d+)$', line)
        if m:
            found_fileID = True
            temp_fileID = int(m.group(1))
    return ret[0]
def parse_files(s, regex=r'^\s+Filename: (.+).(mp4|3gp)$'):
    """Returns a tuple representing the IDs, filenames, and file sizes of
    mtp-files output."""
    # Some preparation.
    ret = set()
    found_filename = False
    found_filesize = False
    found_fileID = False
    # Loop.
    temp_fileID, temp_filename = None, None
    for line in s.split("\n"):
        # If this variable is set, it means the previous line was a file ID,
        # and so this line should be a filename; if this turns out ending up
        # not being the case, something went wrong.
        if found_fileID and not found_filename:
            m = re.match(regex, line)
            if m:
                found_filename = True
                temp_filename = m.group(1) + '.' + m.group(2)
                continue
        if found_fileID and found_filename:
            m = re.match(r'^\s+File size (\d+)\s+.+$', line)
            if m:
                file_size = int(m.group(1))
                new_val = (temp_fileID, temp_filename, file_size)
                ret.add(new_val)
                found_fileID = found_filename = False
                continue
        # Find the "File ID:" line.
        m = re.match(r'^File ID: (\d+)$', line)
        if m:
            found_fileID = True
            temp_fileID = int(m.group(1))
    return ret

def detect():
    """uses fabric's sudo()"""
    cmd_str = "mtp-detect"
    with fabsettings(hide('stdout')):
        result = sudo(cmd_str,shell=True)
    if not result.succeeded:
        print "Command failed to run."
        return False
    sleep(1)
    '''success_detect_regex = r'^$'
    m = re.match(regex, str(result))
    if not m:
        print "Was not a successful run."
        return False'''
    return True
def detect2():
    """uses subprocess"""
    cmd_str = "sudo mtp-detect"
    print "Running: %s" % cmd_str
    try: result = subprocess.check_output(shlex.split(cmd_str))
    except subprocess.CalledProcessError as e:
        log.error("Could not execute: %s" % str(e))
        return False
    '''success_detect_regex = r'^$'
    m = re.match(regex, str(result))
    if not m:
        print "Was not a successful run."
        return False'''
    return True

def mtp_file_list():
    """
    Returns the output of 'mtp-files' as a Python list.

    Uses fabric's sudo function.
    """
    cmd_str = "mtp-files"
    result = sudo(cmd_files_str, pty=False)
    if not result.succeeded:
        print "Unable to do mtp-files."
        return False
    the_files = parse_files(str(result))
    return the_files
def mtp_file_list2():
    """
    Returns the output of 'mtp-files' as a Python list.

    Uses subprocess.
    """
    cmd_str = "sudo mtp-files"
    try: result = subprocess.check_output(shlex.split(cmd_str))
    except subprocess.CalledProcessError as e:
        log.error("Could not execute: %s" % str(e))
        return False, None
    the_files = parse_files(result)
    return True, the_files

def run_cmd(cmd_str):
    log.debug("Running: %s" % cmd_str)
    try: result = subprocess.check_output(shlex.split(cmd_str))
    except subprocess.CalledProcessError as e:
        msg = "Could not execute: %s" % str(e)
        return False, msg
    return True, result
def delete_file(filename):
    cmd_str = "sudo mtp-connect --delete %s" % os.path.split(filename)[1]
    rval, result = run_cmd(cmd_str)
    if rval and result.find('No devices.') != -1: return False
    return rval

def download_android_file(filename=None):
    """Downloads a particular file via MTP."""
    cmd_str = "sudo mtp-files"
    try: result = subprocess.check_output(shlex.split(cmd_str))
    except subprocess.CalledProcessError as e:
        log.error("Could not execute: %s" % str(e))
        return False, None
    fid = parse_files2(result, filename)[0]
    cs = "sudo mtp-connect --getfile %d %s" % (fid, filename)
    log.info("Running: %s" % cs)
    return subprocess.check_output(shlex.split(cs))
def _process_file(fid, fn, fs):
    # Check if file is already there, and check the size; if they are the
    # same, we can just delete the file from the phone..
    if os.path.exists(fn):
        st = os.stat(fn)
        size = st.st_size
        if size == fs:
            log.debug("File is present and equal in size; not copying.")
            if delete and not delete_file(fn):
                log.error("Could not delete file: %s." % fn)
        else:
            log.error("Sizes not equal: %d %d" % (size, fs))
            return False
    # ..otherwise, download the file.  And then delete from phone if we
    # need to.
    else:
        log.info("File %s not already present; downloading." % fn)
        cs = "sudo mtp-connect --getfile %d %s" % (fid, fn)
        log.info("Running: %s" % cs)
        r = subprocess.check_output(shlex.split(cs))
        log.info("Done running: %d." % len(r))
        if delete and not delete_file(fn):
            log.error("Could not delete file from phone: %s." % fn)
    return True
def download_android_media(o=None, delete=False):
    """Downloads files from an Android device."""
    if not o: o = settings.LIFELOG_DATA_PATH
    else: o = os.path.abspath(o)
    # Get list of files to consider.
    log.debug("Getting file list.")
    rval, fl = mtp_file_list2()
    if not rval: return False
    # Download each file.
    log.debug("Downloading each file.")
    for fid, fn, fs in fl:
        fn = os.path.abspath(os.path.join(o, fn))
        log.debug("Processing: %s" % fn)
        if not _process_file(fid, fn, fs):
            log.error("Could not process file: %s." % fn)
        else: sleep(0.5)
