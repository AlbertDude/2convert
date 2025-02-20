#! /usr/bin/env python3

"""
Batch conversion of audio files
  - put files in the folders: [2wav, 2mp3, 2flac] and run this script
  - contents of those folders will be converted to their respective formats
  - sets tags in target mp3 files using 2 mechanisms
     - embedded in the source file (takes precedence)
     - from the filepath folder heirarchy and filename:
        genre/artist/year-album/track_title
  - place jpeg image file in folder to embed (for mp3 only)

Usage:
    ./2convert.py preview
    ./2convert.py go

Requirements:
- system installation of:
  - flac (wav->flac, flac->wav)
  - lame (->mp3)
  - sox (mp3->wav) (probably requires sox mp3 module)
  - ffmpeg (mp3->wav) (alternative)

TODO: 
- print n/M progress
"""

import sys, os
import glob
import subprocess
import time
import re
import argparse
import shutil
import multiprocessing as MP
from multiprocessing.pool import ThreadPool


# Helpers
def all_files(path, ext_list=None): #{
    """ Returns (flat) list of all files in the specified path (recursive)
        option to specify list of desired file extensions, default is no file ext restrictions
        file extensions are case-insensitive and should include the '.'
        e.g. ['.mp3']
    """
    if ext_list:
        lc_ext_list = [e.lower() for e in ext_list]
        return _all_files(path, lc_ext_list)
    else:
        return _all_files(path, None)
#}

def _all_files(path, ext_list=None): #{
    """ Recursive function that generates flat list of all files in the specified path
        option to specify list of desired file extensions, default is no file ext restrictions
    """
    result = []
    fix_path = str(path).replace('[','[[]') # fix glob.glob's handling of square brackets
    try:
        node = glob.glob( fix_path )[0]  
    except:
        print("\nERROR: Unable to open: " + fix_path)
        sys.exit(2)
    if os.path.isfile(node):
        if ext_list:
            if os.path.splitext( str(node) )[1].lower() in ext_list:
                result += [node]
        else:
            result += [node]
    else:
        # it's a folder -- recurse into it
        for node in glob.glob(fix_path + '/*'):
            result += all_files(node, ext_list)
    return result
#}


def check_subprocess_status(cmd, process): #{
    """ Helper to check return code of subprocess call
        Return bool indicating OK (True=OK)
    """
    pout, perr = process.communicate()
    assert process.returncode != None
    if process.returncode != 0:
        from inspect import currentframe, getframeinfo
        frame = currentframe().f_back
        print()
        print("FILE:", getframeinfo(frame).filename)
        print("LINE:", frame.f_lineno)
        print("External command failed:", cmd)
        print("Return code:", process.returncode)
        print("Stdout:\n", pout)
        print("Stderr:\n", perr)
        return False
    return True
#}

def get_tag_info_from_path(path, src_folder): #{
    """ Get tag information from file path
        Expected format:
            genre/artist/year<SEP>album/tracknumber<SEP>title
            - underscores converted to spaces
            - <SEP> flexibly defined: spaces, underscores, dashes, periods
            - subfolders are optional, though they must be in the specified order. So
                - genre/artist/year<SEP>album
                - artist/year<SEP>album
                - year<SEP>album
                are the 3 valid subfolder arrangements
    """

    text_pattern      = r"([a-zA-Z _\d.()']+)"
    text_dash_pattern = r"([a-zA-Z _\d.()'-]+)"
    def parse2(s, field1_name, field2_name): #{
        numeric_pattern = r"([\d]+)"
        sep_pattern     = r"[- _.]+"
        info = {}
        m = re.match(numeric_pattern+sep_pattern+text_dash_pattern, s)
        if m is not None:
            info[field1_name] = m.group(1)
            info[field2_name] = m.group(2)
        else:
            m = re.match(text_pattern, s)
            if m is not None:
                info[field2_name] = m.group(1)
            else:
                print("Can't parse %s from foldername:"%field2_name, s)
        return info
    #}
    def parse1(s, field_name): #{
        info = {}
        m = re.match(text_pattern, s)
        if m is not None:
            info[field_name] = m.group(1)
        else:
            print("Can't parse %s from foldername:"%field_name, s)
        return info
    #}

    class Parse2Wrapper: #{
        """ Parse function wrapper
            This allows us to reuse a common parse2 function for multiple fields
        """
        def __init__(self, field1_name, field2_name):
            self.field1_name = field1_name
            self.field2_name = field2_name

        def __call__(self, *args, **kwargs):
            return parse2(field1_name=self.field1_name, field2_name=self.field2_name, *args, **kwargs)
    #}
    class Parse1Wrapper: #{
        """ Parse function wrapper
            This allows us to reuse a common parse1 function for multiple fields
        """
        def __init__(self, field_name):
            self.field_name = field_name

        def __call__(self, *args, **kwargs):
            return parse1(field_name=self.field_name, *args, **kwargs)
    #}

    fields = [] # list of filename & subfolder names
    p = os.path.splitext(path)[0]
    p, f = os.path.split(p)
    fields.append(f)
    while p:
        p, f = os.path.split(p)
        if f == src_folder:
            break
        else:
            fields.append(f)
        if p == '/':
            break
            
    parse_fcn_lookup = [
        Parse2Wrapper("TRACKNUMBER", "TITLE"),
        Parse2Wrapper("DATE", "ALBUM"),
        Parse1Wrapper("ARTIST"),
        Parse1Wrapper("GENRE"),
        ]
    tag_info = {}
    for f, parse_fcn in zip(fields, parse_fcn_lookup):
        info = parse_fcn(f)
        tag_info.update(info)

    return tag_info
#}

def get_tag_info_from_file(path): #{
    """ Get tag information from file
        Uses SoX --info and then parses its output
        - note: this does not return info about album art ("APIC")
    """

    cmd=['sox','--info'] + [path]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    pout, perr = p.communicate()

    tag_info = {}
    process_comments = False
    lines = pout.decode("utf-8").split('\n')
    for line in lines:
        if process_comments:
            m = re.match(r"([a-zA-Z_]+)=([a-zA-Z _\d.()'-]+)", line)
            if m is not None:
                tag_info[m.group(1)] = m.group(2)
        else:
            m = re.match('Comments[ ]+:', line)
            if m is not None:
                process_comments = True

    return tag_info
#}

def to_mp3(path, options=[], preview=False, img_file=None): #{
    """ Convert input file to mp3
        default command:
            lame -V2 path
        Tries to extract tags:
         - embedded in the file (takes precedence)
         - from the filepath
    """
    assert os.path.isfile(path)
    sys.stdout.write( "-> MP3: " + path + "\n" )
    default_options=['-V2']

    # extract tags from file (these take precedence)
    tag_info = get_tag_info_from_file(path)
    # extract tags from filepath
    addtl_tags = get_tag_info_from_path(path, '2mp3')
    for k, v in addtl_tags.items():
        if k not in tag_info:
            tag_info[k] = v

    tag_lookup = {
        'TITLE': '--tt',
        'ARTIST': '--ta',
        'ALBUM': '--tl',
        'DATE': '--ty',
        'TRACKNUMBER': '--tn',
        'GENRE': '--tg',
        }
    tag_options = []
    for k, v in tag_info.items():
        if k in tag_lookup:
            tag_options.extend( [tag_lookup[k], v] )
    if img_file :
        tag_options.extend( ['--ti', img_file] )
    cmd=['lame'] + default_options + tag_options + options + [path]
    if not preview:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        status = check_subprocess_status(cmd, p)
    else:
        sys.stdout.write( "  " + str(cmd) + "\n" )
        #sys.stdout.write( "  " + str(tag_info) + "\n" )
    return True
#}

def to_wav(path, options=[], preview=False, img_file=None): #{
    assert os.path.isfile(path)

    base, ext = os.path.splitext(path)
    cmd = None
    if ext.lower() == '.flac':
        default_options=[]
        cmd=['flac', '-d'] + default_options + options + [path]
    elif ext.lower() == '.mp3':
        default_options=[]
        wav_path = base+'.wav'
        cmd=['sox'] + default_options + options + [path, wav_path]
    elif ext.lower() == '.wav': # already a wave file
        pass
    else:
        print("Don't know how to handle filetype (%s): %s"%(ext,path))

    if cmd:
        sys.stdout.write( "-> WAV: " + path + "\n" )
        if not preview:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            status = check_subprocess_status(cmd, p)
        else:
            sys.stdout.write( "  " + str(cmd) + "\n" )
    return True
#}

def flac_to_flac(path, options=[], preview=False, img_file=None): #{
    """ Re-encode flac file
        why? -- some flac files cause LAME front-end to decode to noise
        - not sure what the exact cause is
        - just know that a flac re-encode seems to fix it
        This could be a one line flac command but 
        - it turns out that old flac files that use ID3v2 tags cause an error with the one line flac command.
        So instead, original flac is decoded to temp wav file which is then re-encoded
        - additionally try to extract and transfer tags
        Since both the original and new flac will exist in the same folder temporarily, the original
        file is renamed first and the new file will be written
        folder
    """
    # Decode original flac to temp wav file
    import uuid
    temp_wav_filename = str(uuid.uuid4()) + ".wav"
    cmd=['flac', '-d', path, '-o', temp_wav_filename]
    if not preview:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        status = check_subprocess_status(cmd, p)
    else:
        sys.stdout.write( "  " + str(cmd) + "\n" )
        #sys.stdout.write( "  " + str(tag_info) + "\n" )

    # Get tag_info from original flac
    tag_info = get_tag_info_from_file(path)

    # Encode temp wav file to new flac file
    sys.stdout.write( "->FLAC: " + path + "\n" )
    default_options=['-8', '--replay-gain']
    tag_options = []
    for k, v in tag_info.items():
        tag_options.append( '--tag=%s=%s'%(k, v) )
    new_flac_name = os.path.splitext(path)[0] + '_.flac'
    cmd=['flac'] + default_options + tag_options + options + [temp_wav_filename, '-o', new_flac_name]
    if not preview:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        status = check_subprocess_status(cmd, p)
    else:
        sys.stdout.write( "  " + str(cmd) + "\n" )
        #sys.stdout.write( "  " + str(tag_info) + "\n" )

    # Delete temp wav file
    if not preview:
        os.remove(temp_wav_filename)
    else:
        sys.stdout.write( "  deleting temp wav file:" + temp_wav_filename + "\n" )
#}

def to_flac(path, options=[], preview=False, img_file=None): #{
    """ Convert input wave file to flac
        default command:
            flac path
        Tries to extract tags from the filepath
        - since only .wav files should be converted to flac, there are no embedded tags available
    """
    assert os.path.isfile(path)

    ext = os.path.splitext(path)[1].lower()

    assert ext != '.mp3'  # don't convert MP3s to flac...

    # re-encode flac?
    if ext == '.flac':
        return flac_to_flac(path, options, preview, img_file)

    # encode wav
    if ext != '.wav':  # skip non-wav files
        return True
    sys.stdout.write( "->FLAC: " + path + "\n" )
    default_options=['-8', '--replay-gain']
    tag_info = get_tag_info_from_path(path, '2flac')
    tag_options = []
    for k, v in tag_info.items():
        tag_options.append( '--tag=%s=%s'%(k, v) )
    cmd=['flac'] + default_options + tag_options + options + [path]
    if not preview:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        status = check_subprocess_status(cmd, p)
    else:
        sys.stdout.write( "  " + str(cmd) + "\n" )
        #sys.stdout.write( "  " + str(tag_info) + "\n" )
    return True
#}

class FuncWrapper:
    """ Function wrapper
        Reason for being is to provide a callable function-like object with definable properties:
        - queryable output type
    """
    def __init__(self, f, output_type):
        self.f = f
        self.output_type = output_type

    def __call__(self, *args, **kwargs):
        return self.f(*args, **kwargs)

    def get_output_type(self):
        return self.output_type
        

def process_case(args_tuple): #{
    """ Wrapper to facilitate multi-thread implementation
    """
    (path, fcn, options, preview, img_file) = args_tuple
    fcn( path, preview=preview, img_file=img_file )
    # move source file to done folder (keeping folder heirarchy)
    remaining = os.path.dirname(path)
    while remaining:
        remaining, folder = os.path.split(remaining)

    dest_path = os.path.join('done', path.split(folder+'/')[1])
    if preview:
        print("MOVE:", path, '-->\n     ', dest_path)
    else:
        dest_folder = os.path.dirname(dest_path)
        try:
            os.makedirs(dest_folder)
        except OSError:
            if not os.path.isdir(dest_folder):
                raise
        shutil.move(path, dest_path)
#}

USE_MULTIPLE_THREADS = True

def main(args): #{
    global USE_MULTIPLE_THREADS
    command              = args.command
    jobs_adjustment      = args.jobs_adjustment

    num_cpus = MP.cpu_count()    
    num_jobs = max(num_cpus + jobs_adjustment, 1)    # minimum of at least 1 job
    print()
    print("Num CPUs detected:", num_cpus)
    print("Num jobs to use  :", num_jobs)
    print()

    start_time = time.time()

    conv_fcn_lut = {
        '2mp3'  : FuncWrapper(to_mp3, 'mp3'),
        '2wav'  : FuncWrapper(to_wav, 'wav'),
        '2flac' : FuncWrapper(to_flac, 'flac'),
        }
    src_folders = list(conv_fcn_lut.keys())

    cases = []
    for folder in src_folders:
        fcn = conv_fcn_lut[folder]
        if fcn:
            f_list = all_files(folder)
            f_count = 0
            for f in f_list:
                if os.path.splitext( f )[1].lower() != '.jpg' :
                    img_list  = glob.glob( os.path.join( os.path.split(f)[0], "*.jpg") )
                    img_list += glob.glob( os.path.join( os.path.split(f)[0], "*.JPG") )
                    img_file = img_list[0] if ( len( img_list ) > 0 ) else None
                    cases.append( (f, fcn, None, command=='preview', img_file) )
                    f_count += 1
            print(f_count, "files from folder", "(%s)"%folder, "to be converted to", fcn.get_output_type())

    if command=='preview':
        USE_MULTIPLE_THREADS = False

    print()
    if USE_MULTIPLE_THREADS:
        pool = ThreadPool(num_jobs)
        pool.map(process_case, cases)
        pool.close()
        pool.join()
    else:
        for case in cases:
            process_case(case)

    end_time = time.time()
    print()
    print("Time taken: %.1f seconds" % (end_time - start_time))
#}

if __name__ == '__main__' : #{
    parser = argparse.ArgumentParser()

    parser.add_argument("command", help="[go|preview]")
    parser.add_argument("-ja",  "--jobs_adjustment", type=int, default=0, 
                        help="adjustment to default number of jobs (default=0)")

    args = parser.parse_args()
    main(args)
#}


