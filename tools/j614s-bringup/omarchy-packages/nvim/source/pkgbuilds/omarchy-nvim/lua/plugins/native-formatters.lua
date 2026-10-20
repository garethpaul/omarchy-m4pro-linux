-- These formatters come from native system packages, not the builder's Mason
-- cache. Keep other tools requested by LazyVim extras or the user unchanged.
return {
  {
    "mason-org/mason.nvim",
    opts = function(_, opts)
      local tools = {}
      for _, tool in ipairs(opts.ensure_installed or {}) do
        if tool ~= "shfmt" and tool ~= "stylua" then
          tools[#tools + 1] = tool
        end
      end
      opts.ensure_installed = tools
    end,
  },
}
