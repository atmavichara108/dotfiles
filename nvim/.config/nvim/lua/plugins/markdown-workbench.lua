local function open_with_glow()
  if vim.fn.executable("glow") ~= 1 then
    vim.notify("Glow не установлен: внешний просмотр недоступен", vim.log.levels.WARN)
    return
  end

  local path = vim.api.nvim_buf_get_name(0)
  if path == "" then
    vim.notify("Glow требует сохранённый Markdown-файл", vim.log.levels.WARN)
    return
  end

  vim.cmd("botright new")
  local job = vim.fn.termopen({ "glow", "--pager", "--", path })
  if job <= 0 then
    vim.notify("Не удалось запустить Glow", vim.log.levels.ERROR)
    vim.cmd("close")
    return
  end
  vim.cmd("startinsert")
end

return {
  {
    "nvim-treesitter/nvim-treesitter",
    opts = function(_, opts)
      opts.ensure_installed = opts.ensure_installed or {}
      for _, parser in ipairs({ "markdown", "markdown_inline" }) do
        if not vim.tbl_contains(opts.ensure_installed, parser) then
          table.insert(opts.ensure_installed, parser)
        end
      end
    end,
  },
  {
    "MeanderingProgrammer/render-markdown.nvim",
    ft = "markdown",
    opts = {
      enabled = true,
      file_types = { "markdown" },
      render_modes = { "n", "c", "t" },
      heading = { enabled = true },
      bullet = { enabled = true },
      checkbox = { enabled = true },
      pipe_table = { enabled = true },
      callout = {},
      code = { enabled = true, inline = true },
    },
    keys = {
      {
        "<leader>mp",
        "<cmd>RenderMarkdown buf_toggle<cr>",
        ft = "markdown",
        desc = "Markdown: toggle render",
      },
      {
        "<leader>mP",
        "<cmd>RenderMarkdown buf_enable<cr>",
        ft = "markdown",
        desc = "Markdown: enable render",
      },
      {
        "<leader>mg",
        open_with_glow,
        ft = "markdown",
        desc = "Markdown: open in Glow",
      },
    },
  },
}
