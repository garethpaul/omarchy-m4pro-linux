vim.opt.runtimepath:prepend('/conform')
local conform = require('conform')
local qemu = '/usr/bin/qemu-aarch64-static'
local options = {ensure_installed={'stylua','shfmt','shellcheck'}, PATH='prepend'}
dofile('/native-formatters.lua')[1].opts(nil, options)
assert(table.concat(options.ensure_installed, ',') == 'shellcheck')
assert(options.PATH == 'prepend')
conform.setup({
  log_level=vim.log.levels.DEBUG,
  notify_on_error=true,
  notify_no_formatters=true,
  formatters_by_ft={sh={'shfmt'},lua={'stylua'}},
  formatters={
    shfmt={command=qemu,prepend_args={'-L','/','/usr/bin/shfmt'}},
    stylua={command=qemu,prepend_args={'-L','/','/usr/bin/stylua'}},
  },
})
local config=assert(io.open('/work/.stylua.toml','w'))
config:write('indent_type = "Spaces"\nindent_width = 2\n');config:close()
local results={}
local function format_file(name, filetype, input, expected, formatter)
  local buf=vim.api.nvim_create_buf(true,false)
  vim.api.nvim_buf_set_name(buf,'/work/'..name)
  vim.bo[buf].filetype=filetype
  vim.bo[buf].expandtab=true
  vim.bo[buf].shiftwidth=2
  vim.api.nvim_buf_set_lines(buf,0,-1,false,input)
  local selected=conform.list_formatters(buf)
  assert(#selected==1 and selected[1].name==formatter and selected[1].available)
  assert(selected[1].command==qemu)
  local first_callback=false
  local attempted=conform.format({bufnr=buf,async=false,timeout_ms=10000,lsp_format='never'},function(err,did_edit)
    assert(err==nil,tostring(err));assert(did_edit==true);first_callback=true
  end)
  assert(attempted and first_callback)
  assert(vim.deep_equal(vim.api.nvim_buf_get_lines(buf,0,-1,false),expected))
  local second_callback=false
  assert(conform.format({bufnr=buf,async=false,timeout_ms=10000,lsp_format='never'},function(err,did_edit)
    assert(err==nil,tostring(err));assert(did_edit==false);second_callback=true
  end))
  assert(second_callback)
  assert(vim.deep_equal(vim.api.nvim_buf_get_lines(buf,0,-1,false),expected))
  results[#results+1]={filetype=filetype,automatic_selected=selected[1].name,command=selected[1].command,
    actual=vim.api.nvim_buf_get_lines(buf,0,-1,false),first_callback=true,idempotent_callback=true}
  return buf
end
local shellbuf=format_file('fixture.sh','sh',{'if true;then','echo "arm64"','fi'},
 {'if true; then','  echo "arm64"','fi'},'shfmt')
format_file('fixture.lua','lua',{'local  x={1,2}','return x'},{'local x = { 1, 2 }','return x'},'stylua')
-- A real unavailable command must not be offered or run, and must not edit.
conform.formatters.shfmt.command='/usr/bin/not-present'
local before=vim.api.nvim_buf_get_lines(shellbuf,0,-1,false)
local unavailable=conform.list_formatters(shellbuf)
assert(#unavailable==0)
assert(conform.get_formatter_info('shfmt',shellbuf).available==false)
local attempted=conform.format({bufnr=shellbuf,async=false,lsp_format='never',quiet=true})
assert(attempted==false)
assert(vim.deep_equal(before,vim.api.nvim_buf_get_lines(shellbuf,0,-1,false)))
local output=assert(io.open('/work/observations.json','w'))
output:write(vim.json.encode({status='PASS',real_conform=true,cases=results,
  unavailable_command_refused=true, options_callback_pass=true,
  scope='Real Conform filetype selection, builtin args, runner, buffer edits and idempotence; explicit QEMU prefix override'}))
output:close()
vim.cmd('qa!')
