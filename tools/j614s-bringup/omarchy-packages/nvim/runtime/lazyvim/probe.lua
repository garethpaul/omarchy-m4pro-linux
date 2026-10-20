local uv = vim.uv or vim.loop
local stages, fixtures = {}, {}
local function attempt(name, fn)
  local ok, value = pcall(fn)
  stages[name] = {ok = ok, value = ok and value or tostring(value)}
end
vim.wait(500, function() return false end, 20)
attempt('mason_command', function() vim.cmd('Mason'); return true end)
require('mason.settings').current.log_level = vim.log.levels.DEBUG -- Observability only.
attempt('curl_offline', function()
  return vim.system({'/usr/bin/curl', '-fsSL', '--connect-timeout', '2', 'https://api.github.com/repos/mason-org/mason-registry/releases/latest'}, {text = true}):wait(4000)
end)
vim.wait(500, function() return false end, 20)
attempt('mason_resolved_options', function() return LazyVim.opts('mason.nvim') end)
for _, fixture in ipairs({
  {name = 'shell', path = '/work/fixture.sh', lines = {'if true;then echo arm64;fi'}},
  {name = 'lua', path = '/work/fixture.lua', lines = {'local x={1,2}', 'return x'}},
}) do
  attempt(fixture.name, function()
    vim.fn.writefile(fixture.lines, fixture.path)
    vim.cmd('edit '..fixture.path)
    local buf = vim.api.nvim_get_current_buf()
    vim.wait(500, function() return false end, 20)
    local conform = require('conform')
    require('conform.log').level = vim.log.levels.DEBUG -- Observability only.
    local ret = {filetype = vim.bo[buf].filetype, selected = conform.list_formatters(buf),
      before = vim.api.nvim_buf_get_lines(buf, 0, -1, false), buffer = buf}
    local function format()
      local response = {}
      conform.format({bufnr = buf, async = false}, function(err, did_edit)
        response.callback = true; response.error = err and vim.inspect(err) or ''; response.did_edit = did_edit
      end)
      response.lines = vim.api.nvim_buf_get_lines(buf, 0, -1, false)
      return response
    end
    ret.first = format();ret.second = format();fixtures[fixture.name] = ret
    return true
  end)
end
local status = table.concat(vim.fn.readfile('/proc/self/status'), '\n')
local result = {stages = stages, fixtures = fixtures,
  scope = 'Full packaged startup observation, no native target or transaction claim', errmsg = vim.v.errmsg,
  messages = vim.api.nvim_exec2('messages', {output = true}).output,
  executable = {}, runtime = vim.api.nvim_list_runtime_paths(), home_env_absent = vim.env.HOME == nil,
  host_home_absent = not uv.fs_stat('/home') and not uv.fs_stat('/root'), cap_eff_zero = status:match('CapEff:%s*0000000000000000') ~= nil,
  route_table = table.concat(vim.fn.readfile('/proc/net/route'), '\n'), loaded = {}, errors = {}}
for _, name in ipairs({'git','shfmt','stylua','curl'}) do
  result.executable[name] = {available = vim.fn.executable(name), path = vim.fn.exepath(name)}
end
local readonly, readonlyerr = uv.fs_open('/usr/bin/shfmt', 'w', 420)
result.input_readonly = readonly == nil and readonlyerr:match('EROFS') ~= nil
if readonly then uv.fs_close(readonly) end
local ok, config = pcall(require, 'lazy.core.config');result.lazy_config_loaded = ok
if ok then
  for name, plugin in pairs(config.plugins) do result.loaded[name] = plugin._ and plugin._.loaded ~= nil or false end
  result.plugin_count = vim.tbl_count(config.plugins)
end
for _, name in ipairs({'mason','conform','lazyvim'}) do result[name..'_loaded'] = package.loaded[name] ~= nil end
result.mason_packages_present = uv.fs_stat('/work/data/nvim/mason/packages') ~= nil
vim.fn.writefile({vim.json.encode(result)}, '/work/observations.json')
vim.cmd('qa!')
