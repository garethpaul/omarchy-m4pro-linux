local uv = vim.uv
local observations = {}
for _, path in ipairs({ '/qemu', '/usr/bin/shfmt', '/usr/bin/stylua', '/usr/bin/nvim' }) do
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
vim.cmd('qa!')
