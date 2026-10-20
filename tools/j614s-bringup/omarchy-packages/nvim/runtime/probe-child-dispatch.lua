local uv = vim.uv
local checks = {}
checks.home_env_absent = uv.os_getenv('HOME') == nil
checks.host_home_absent = uv.fs_stat('/home') == nil and uv.fs_stat('/root') == nil
checks.only_sandbox_commands = vim.fn.exepath('shfmt') == '/usr/bin/shfmt'
  and vim.fn.exepath('stylua') == '/usr/bin/stylua'
local fd, ro_error = uv.fs_open('/native-formatters.lua', 'a', 420)
checks.input_read_only = fd == nil and ro_error:find('EROFS', 1, true) ~= nil
if fd then uv.fs_close(fd) end
local fd2, write_error = uv.fs_open('/work/owned-output', 'w', 420)
assert(fd2, write_error)
uv.fs_write(fd2, 'owned sandbox scratch\n', 0)
uv.fs_close(fd2)
checks.scratch_writable = true
local function read(path)
  local file = assert(io.open(path, 'r'))
  local value = file:read('*a')
  file:close()
  return value
end
local route = read('/proc/net/route')
checks.no_network_routes = not route:match('\n[^\n]+\n[^\n]+')
local status = read('/proc/self/status')
checks.no_capabilities = status:match('CapEff:%s+0+\n') ~= nil
local specifications = dofile('/native-formatters.lua')
assert(#specifications == 1)
assert(specifications[1][1] == 'mason-org/mason.nvim')
local options = { ensure_installed = { 'stylua', 'shfmt', 'shellcheck', 'lua-language-server' }, PATH = 'prepend' }
specifications[1].opts(nil, options)
checks.default_tools_removed = table.concat(options.ensure_installed, ',') == 'shellcheck,lua-language-server'
checks.other_options_preserved = options.PATH == 'prepend'
local empty = {}
specifications[1].opts(nil, empty)
checks.empty_options_work = #empty.ensure_installed == 0
-- Explicit QEMU child dispatch is needed without changing host binfmt rules.
-- This exercises Neovim's real subprocess path, not Conform/Mason loading.
local diagnostic = assert(io.open('/work/dispatch-diagnostic.json', 'w'))
diagnostic:write(vim.json.encode({qemu_stat=uv.fs_stat('/qemu'), qemu_executable=vim.fn.executable('/qemu'), shfmt_executable=vim.fn.executable('/usr/bin/shfmt'), qemu_path=vim.fn.exepath('/qemu')}))
diagnostic:close()
local sh = vim.fn.system({ '/qemu', '-L', '/', '/usr/bin/shfmt', '-i', '2' }, 'if true;then echo "arm64";fi\n')
checks.neovim_shfmt_subprocess = vim.v.shell_error == 0 and sh == 'if true; then echo "arm64"; fi\n'
local lua = vim.fn.system({ '/qemu', '-L', '/', '/usr/bin/stylua', '--indent-type', 'Spaces', '--indent-width', '2', '-' }, 'local  x={1,2}\nreturn x\n')
checks.neovim_stylua_subprocess = vim.v.shell_error == 0 and lua == 'local x = { 1, 2 }\nreturn x\n'
local output = assert(io.open('/work/probe.json', 'w'))
output:write(vim.json.encode({ checks = checks, readonly_error = ro_error, formatter_outputs = { shfmt = sh, stylua = lua },
  route_table = route, home_lookup = uv.os_homedir(),
  scope = 'Actual ARM Neovim Lua options callback only; no Mason, Conform or LazyVim loader' }))
output:close()
for name, passed in pairs(checks) do assert(passed, name) end
vim.cmd('qa!')
