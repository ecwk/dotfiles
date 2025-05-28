return {
  "williamboman/mason.nvim",
  "williamboman/mason-lspconfig.nvim",
  {
    "neovim/nvim-lspconfig",
    dependencies = {
      "mason.nvim",
      "mason-lspconfig.nvim",
    },
    config = function()
      require("mason").setup()
      require("mason-lspconfig").setup({
        ensure_installed = {
          "pyright",
          "rust_analyzer",
          "ts_ls",
          "html",
          "cssls",
          "lua_ls",
        },
      })
    end
  },
  {
    "ray-x/lsp_signature.nvim",
    event = "InsertEnter",
    enabled = false,
    opts = {
      move_cursor_key = "<M-k>",
    }
  }
}
