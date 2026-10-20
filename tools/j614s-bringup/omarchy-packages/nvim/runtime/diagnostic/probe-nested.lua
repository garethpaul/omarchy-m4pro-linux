local uv = vim.uv
local observations = {}
for _, path in ipairs({ '/qemu', '/usr/bin/qemu-aarch64-static', '/usr/bin/shfmt', '/usr/bin/stylua', '/usr/bin/nvim' }) do
  local stat, stat_error, stat_code = uv.fs_stat(path)
  local access, access_error, access_code = uv.fs_access(path, 'X')
  local fd, open_error = uv.fs_open(path, 'r', 0)
  local header
  if fd then
    local bytes = assert(uv.fs_read(fd, 64, 0))
    header = (bytes:gsub('.', function(c) return string.format('%02x', string.byte(c)) end))
    uv.fs_close(fd)
  end
  observations[path] = { stat = stat, stat_error = stat_error, stat_code = stat_code,
    access = access, access_error = access_error, access_code = access_code,
    open_error = open_error, header_hex = header,
    executable = vim.fn.executable(path), exepath = vim.fn.exepath(path) }
end
local fd = assert(io.open('/work/observations.json', 'w'))
fd:write(vim.json.encode({observations = observations, uid = uv.getuid(),
  home_env_absent = uv.os_getenv('HOME') == nil}))
fd:close()
assert(observations['/qemu'].access == true)
assert(observations['/qemu'].executable == 0)
assert(observations['/usr/bin/qemu-aarch64-static'].executable == 1)
assert(observations['/qemu'].header_hex == observations['/usr/bin/qemu-aarch64-static'].header_hex)
local function format(args, input, expected)
  local result = vim.fn.system(args, input)
  assert(vim.v.shell_error == 0, 'native formatter subprocess exit')
  assert(result == expected, result)
  return result
end
local specifications = dofile('/native-formatters.lua')
local options = {ensure_installed={'stylua','shfmt','shellcheck'}, PATH='prepend'}
specifications[1].opts(nil, options)
assert(table.concat(options.ensure_installed, ',') == 'shellcheck')
assert(options.PATH == 'prepend')
local qemu = '/usr/bin/qemu-aarch64-static'
local sh_input = 'if true;then echo "arm64";fi\n'
local sh_expected = 'if true; then echo "arm64"; fi\n'
local sh_args = { qemu, '-L', '/', '/usr/bin/shfmt', '-i', '2' }
local sh = format(sh_args, sh_input, sh_expected)
format(sh_args, sh, sh_expected)
local lua_args = { qemu, '-L', '/', '/usr/bin/stylua', '--indent-type', 'Spaces', '--indent-width', '2', '-' }
local lua_expected = 'local x = { 1, 2 }\nreturn x\n'
local lua = format(lua_args, 'local  x={1,2}\nreturn x\n', lua_expected)
format(lua_args, lua, lua_expected)
local output = assert(io.open('/work/observations.json', 'w'))
output:write(vim.json.encode({observations=observations, subprocess={shfmt=sh,stylua=lua,
  first_pass_and_idempotence=true, qemu_path=qemu, options_callback_pass=true}, home_env_absent=uv.os_getenv('HOME')==nil}))
output:close()
vim.cmd('qa!')
