# Disk I/O with change tracking and other features.
import os, io, time, stat, pickle, pathlib, codecs, shutil
from . import global_vars, fittings, paths
tprint = global_vars.tprint

try:
    debug_restrict_disk_modifications_to_these
except:
    debug_restrict_disk_modifications_to_these = None

# Global variables:
  # original_txts = the txt b4 modifications, set in contents_on_first_call and in save.
     # Different than the (kept up-to-date) py_updater.uglobals['filecontents'].
  # checkpoints = Optional feature. Name and save file snapshots.
  # txt_edits = Recorded by record_txt_update, queried by get_txt_edits. Simple list.
fglobals = global_vars.global_get('fileio_globals', {'original_txts':{}, 'txt_edits':[], 'checkpoints':{},'created_files':set()})

#################################Loading########################################

def date_mod(fname):
    fname = paths.abs_path(fname)
    return os.path.getmtime(fname)

def is_hidden(fname):
    fname = paths.abs_path(fname)
    return fname.split('/')[-1][0] == '.'

def fload(fname, bin_mode=False): # Code adapted from Termpylus
    if not os.path.isfile(fname):
        return None
    if bin_mode:
        with io.open(fname, mode="rb") as file_obj:
            return file_obj.read()
    else:
        with io.open(fname, mode="r", encoding="utf-8") as file_obj:
            try:
                x = file_obj.read()
            except UnicodeDecodeError:
                raise Exception('No UTF-8 for:', fname)
            out = paths.linux_if_str(x)
            return out

def contents_on_first_call(fname):
    # The contents of the file on the first time said function was called.
    # OR just before the first time the file was saved.
    fname = paths.abs_path(fname)
    if fname not in fglobals['original_txts']:
        txt = fload(fname)
        if txt is not None:
            fglobals['original_txts'][fname] = txt
        return txt
    return fglobals['original_txts'][fname]

def folder_load(folder_path, initial_path=None, allowed_extensions=None, acc=None):
    # filename => values.
    if acc is None:
        acc = {}
    if initial_path is None:
        initial_path = folder_path
    for filename in os.listdir(folder_path):
        fname = folder_path+'/'+filename
        if os.path.isdir(fname):
            folder_load(fname, initial_path, allowed_extensions, acc)
        else:
            if allowed_extensions is not None:
                if '.' not in filename or filename.split('.')[-1] not in allowed_extensions:
                    continue
            acc[fname[len(initial_path):]] = fload(fname)

    return acc

def python_source_load():
    # Gets the src cache from the current folder, filename => contents with local cache.
    # Looks for all python files within this directory.
    fname2contents = {}
    for root, dirs, files in os.walk(".", topdown=False): # TODO: exclude .git and __pycache__ if the time cost becomes significant.
        for fname in files:
            if fname.endswith('.py'):
                fnamer = paths.rel_path(os.path.join(root, fname))
                fname2contents[fnamer] = fload(fnamer)
    return fname2contents

#####################################Saving#####################################

def pickle64(x):
    # Base 64 pickle, which can be pasted into the command line of i.e. a cloud shell.
    #https://stackoverflow.com/questions/30469575/how-to-pickle-and-unpickle-to-portable-string-in-python-3
    return codecs.encode(pickle.dumps(x), "base64").decode()

def disk_unpickle64(txt64):
    # Unpickels a pickle64 dict from filename to file contents, saving it to the disk.
    # The filenames should be relative paths so that it can work across folders/machines.
    fname2obj = pickle.loads(codecs.decode(txt64.encode(), "base64"))
    for fname, txt in fname2obj.items():
        if txt is None:
            try:
                os.remove(fname)
            except:
                tprint('Warning: file deletion during update failed for',fname)
        else:
            fsave(fname, txt) # auto-makes enclosing folders.
    tprint('Saved to these files:', fname2obj.keys())

def _update_checkpoints_before_saving(fname):
    fname = paths.abs_path(fname)
    if len(fglobals['checkpoints'])==0:
        return
    txt = contents(fname) # May be None, which means reverting = deleting this file.
    for k in fglobals['checkpoints'].keys():
        if fname not in fglobals['checkpoints'][k]:
            fglobals['checkpoints'][k][fname] = txt

def _unwindoze_attempt(f, filename_err_report, tries=12, retry_delay=1, throw_some_errors=False):
    for i in range(tries):
        try:
            f()
            break
        except PermissionError as e:
            if 'being used by another process' in str(e):
                tprint('File-in-use error (will retry) for:', filename_err_report)
            else:
                if throw_some_errors:
                    f() # Throw actual permission errors.
                else:
                    tprint('Will retry because of this PermissionError:', str(e))

            if i==tries-1:
                raise Exception('Windoze error: Retried too many times and this file stayed in use:', filename_err_report)
            time.sleep(retry_delay)

def _fsave1(fname, txt, mode, tries=12, retry_delay=1.0):
    # Does not need any enclosing folders to already exist.
    #https://stackoverflow.com/questions/12517451/automatically-creating-directories-with-file-output
    fname = paths.abs_path(fname)
    def f():
        os.makedirs(os.path.dirname(fname), exist_ok=True)
        with io.open(fname, mode=mode, encoding="utf-8") as file_obj:
            file_obj.write(txt)
    _unwindoze_attempt(f, fname, tries, retry_delay)

def record_txt_update(fname, the_edits):
    # Standard record updates. The edit is of the form [ix0, ix1, inserted_txt]
    t_now = time.time()
    for the_edit in the_edits:
        ed1 = [fname]+the_edit+[t_now]
        fglobals['txt_edits'].append(ed1)

def get_txt_edits():
    return list(fglobals['txt_edits'])

def fsave(fname, txt, tries=12, retry_delay=1.0, update_module=True):
    # Automatically stores the original txts and updates modules if fname cooresponds to a module.
    fname = paths.abs_path(fname)
    bin_mode = type(txt) is bytes
    old_txt = fload(fname, bin_mode=bin_mode)
    _update_checkpoints_before_saving(fname)
    if os.path.exists(fname):
        contents_on_first_call(fname) # Save the old contents.
    else:
        fglobals['created_files'].add(fname)
    _fsave1(fname, txt, "wb" if bin_mode else "w", tries, retry_delay)

    if old_txt != txt:
        the_edits = fittings.txt_edits(old_txt, txt)
        the_edits1 = [[ed[0], ed[1], old_txt[ed[0]:ed[1]], ed[2]] for ed in the_edits]
        record_txt_update(fname, the_edits1)
    if old_txt != txt and update_module: # Update the module if the text changed and the file cooresponds to a module.
        from . import py_updater # This circular dependency would be akward to break.
        from . import modules # This one somewhat less so.
        modulename = None
        module2filename = modules.module_fnames(True) # user_only set to True, is it always safe to do so?
        for modname in module2filename.keys(): # a little inefficient to loop through each modulename.
            if module2filename[modname] == fname:
                modulename = modname
        if modulename:
            py_updater.update_one_module(modulename, fname=fname, assert_main=True)

def fcreate(fname, is_folder):
    # Creates an empty file.
    fname = paths.abs_path(fname)
    if not os.path.exists(fname):
        fglobals['created_files'].add(fname)
    if is_folder:
        folder = fname
    else:
        folder, _ = os.path.split(fname)

    #https://stackoverflow.com/questions/273192/how-can-i-safely-create-a-nested-directory
    pathlib.Path(folder).mkdir(parents=True, exist_ok=True)
    if not is_folder:
        with open(fname,'a') as _:
            pass

def make_folder(foldername):
    os.makedirs(foldername, exist_ok=True)

def fappend(fname, txt):
    fname = paths.abs_path(fname)
    if len(fglobals['checkpoints'])>0: # Requires a load+save.
        fsave(fname, contents(fname)+txt)
    else:
        _fsave1(fname, txt, "ab" if type(txt) is bytes else "a")

def save_checkpoint(name):
    # Save a checkpoint which can be reverted to. Overwrite if name already exists.
    fglobals['checkpoints'][name] = {}

###########################Deleting ############################################

def fdelete(fname):
    # Basic delete which will fail for windows file-in-use errors as well as readonly files in folders.
    if os.path.exists(fname):
        if file_io.is_folder(fname):
            shutil.rmtree(fname)
        else:
            os.unlink(fname)

def power_delete(fname, tries=12, retry_delay=1.0):
    # Can be reverted IF there is a checkpoint saved.
    fname = paths.abs_path(fname)
    if not os.path.exists(fname):
        return
    _update_checkpoints_before_saving(fname)

    if file_io.is_folder(fname):
        for root, dirs, files in os.walk(fname, topdown=False):
            for _fname in files:
                _fname1 = root+'/'+_fname
                def f():
                    os.chmod(_fname1, stat.S_IWRITE)
                _unwindoze_attempt(f, _fname1, tries, retry_delay)
        _unwindoze_attempt(lambda: shutil.rmtree(fname), fname, tries, retry_delay)
    else:
        _unwindoze_attempt(lambda: os.remove(fname), fname, tries, retry_delay)

def clear_pycache(fname):
    fname = paths.abs_path(fname)
    # This can intefere with updating.
    cachefolder = os.path.dirname(fname)+'/__pycache__'
    leaf = os.path.basename(fname).replace('.py','').replace('\\','/')
    if os.path.isdir(cachefolder):
        leaves = os.listdir(cachefolder)
        for l in leaves:
            if leaf in l:
                #print('Deleting cached file:', cachefolder+'/'+l)
                os.remove(cachefolder+'/'+l)

def delete_checkpoint(name):
    if name in fglobals['checkpoints']:
        del fglobals['checkpoints'][name]

def empty_folder(folder, keeplist=None):
    # Ensured folder is empty
    # Useful for installation, since actually deleting the folder can cause problems.
    # https://stackoverflow.com/questions/185936/how-to-delete-the-contents-of-a-folder
    if not os.path.exists(folder):
        os.makedirs(folder)
        return
    for filename in os.listdir(folder):
        if keeplist is not None and filename in keeplist:
            continue
        power_delete(folder+'/'+filename)

############################### Changes to several files at once ###############

def f_impose(fname2txt):
    # Creates or deletes files. Uses fsave, which ensures folders are created if need be.
    for k in fname2txt.keys():
        if fname2txt[k] is None:
            fdelete(fname2txt[k])
        else:
            fsave(k, fname2txt[k])

def copy_with_overwrite(folderA, folderB):
    #Everything in folderA ends up in folderB. Files and folders with the same name are deleted first.
    filesb = set(os.listdir(folderB))
    for fname in os.listdir(folderA):
        filderB = folderB+'/'+fname
        if fname in filesb:
            power_delete(filderB)
        if not os.path.exists(filderB): # Still may exist when ignore_permiss.
            if os.path.isfile(folderA+'/'+fname):
                shutil.copyfile(folderA+'/'+fname, filderB)
            else:
                shutil.copytree(folderA+'/'+fname, filderB)

def revert_checkpoint(check_name):
    # Revert to a given checkpoint.
    fname2txt = fglobals['checkpoints'][check_name].copy() # The copy is important since it is modified inside the for loop!

#################################Debug safety and testing#######################

def _fileallow(fname):
    keeplist = debug_restrict_disk_modifications_to_these
    fname = paths.abs_path(fname)
    if keeplist is not None:
        if type(keeplist) is str:
            keeplist = [keeplist]
        keeplist = [paths.abs_path(kl) for kl in keeplist]
        allow = False
        for k in keeplist:
            if fname.startswith(k):
                allow = True
        return allow
    else:
        return True

def guarded_delete(fname, allow_folders=False, powerful=False):
    # Deleting is dangerous.
    fname = paths.abs_path(fname)
    if not _fileallow(fname):
        raise Exception('debug_restrict_disk_modifications_to_these is set to: '+str(debug_restrict_disk_modifications_to_these).replace('\\\\','/')+' and disallows deleting this filename: '+fname)
    if os.path.isdir(fname) and not allow_folders:
        raise Exception('Attempt to delete folder (and whats inside) when allow_folders=False.')
    power_delete(fname) if powerful else fdelete(fname)

def guarded_create(fname, is_folder):
    # Creating files isn't all that dangerous, but still can be annoying.
    # Skips files that already exist.
    fname = paths.abs_path(fname)
    if not _fileallow(fname):
        raise Exception('debug_restrict_disk_modifications_to_these is set to: '+str(debug_restrict_disk_modifications_to_these).replace('\\\\','/')+' and disallows creating this filename: '+fname)
    fcreate(fname, is_folder)
    return fname

def with_modifications(fname2contents, f, blanck_original_txts=False):
    # Allows temporary file modifications.
    # Runs f with the modified fname2contents.
    cname = '_tmp_with_modifications_checkpoint'; inw = '_inside_with_modifications'
    if fglobals.get(inw,None) is not None:
        raise Exception('Cannot nest with_modifications.')
    fglobals[inw] = True
    original_txts = fglobals['original_txts']
    if blanck_original_txts:
        fglobals['original_txts'] = {}

    save_checkpoint(cname)
    try:
        f_impose(fname2contents)
    except Exception as e:
        revert_checkpoint(cname)
        raise e

    exc = None
    try:
        f()
    except Exception as e:
        exc = e
    revert_checkpoint(cname)
    fglobals[inw] = False
    if blanck_original_txts:
        fglobals['original_txts'] = original_txts
    if exc is not None:
        tprint('Problem inside the function passed to with_modifications (see error below).')
        raise exc
