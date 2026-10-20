/* Exact relevant excerpts from Neovim commit 779c36969e31080503be2dfccbcc3f999e289606.
 * Original line numbers and whole-file hashes: primary-provenance.json.
 * Copyright/licensing: primary-neovim-LICENSE.txt. Not a standalone translation unit.
 */

/* src/nvim/os/fs.c:242-287 */
bool os_can_exe(const char *name, char **abspath, bool use_path)
  FUNC_ATTR_NONNULL_ARG(1)
{
  if (!use_path || gettail_dir(name) != name) {
#ifdef MSWIN
    return is_executable_ext(name, abspath);
#else
    // Must have path separator, cannot execute files in the current directory.
    return ((use_path || gettail_dir(name) != name)
            && is_executable(name, abspath));
#endif
    return false;
  }

  return is_executable_in_path(name, abspath);
}

/// Returns true if `name` is an executable file.
///
/// @param[in]            name     Filename to check.
/// @param[out,allocated] abspath  Returns full exe path, if not NULL.
static bool is_executable(const char *name, char **abspath)
  FUNC_ATTR_NONNULL_ARG(1)
{
  int32_t mode = os_getperm(name);

  if (mode < 0) {
    return false;
  }

#ifdef MSWIN
  // Windows does not have exec bit; just check if the file exists and is not
  // a directory.
  const bool ok = S_ISREG(mode);
#else
  int r = -1;
  if (S_ISREG(mode)) {
    RUN_UV_FS_FUNC(r, uv_fs_access, name, X_OK, NULL);
  }
  const bool ok = (r == 0);
#endif
  if (ok && abspath != NULL) {
    *abspath = save_abs_path(name);
  }
  return ok;
}

/* src/nvim/path.c:1135-1170 */
/// Find end of the directory name
///
/// @param[in]  fname  File name to process.
///
/// @return end of the directory name, on the first path separator:
///
///            "/path/file", "/path/dir/", "/path//dir", "/file"
///                  ^             ^             ^        ^
const char *gettail_dir(const char *const fname)
  FUNC_ATTR_PURE FUNC_ATTR_WARN_UNUSED_RESULT FUNC_ATTR_NONNULL_ALL
{
  const char *dir_end = fname;
  const char *next_dir_end = fname;
  bool look_for_sep = true;

  for (const char *p = fname; *p != NUL;) {
    if (vim_ispathsep(*p)) {
      if (look_for_sep) {
        next_dir_end = p;
        look_for_sep = false;
      }
    } else {
      if (!look_for_sep) {
        dir_end = next_dir_end;
      }
      look_for_sep = true;
    }
    MB_PTR_ADV(p);
  }
  return dir_end;
}

/// Calls globpath() with 'path' values for the given pattern and stores the
/// result in "gap".
/// Returns the total number of matches.
///
