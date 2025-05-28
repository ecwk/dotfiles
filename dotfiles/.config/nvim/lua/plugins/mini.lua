return {
  "echasnovski/mini.nvim",
  version = false, -- main branch
  config = function ()
    require("mini.pairs").setup()
    require("mini.pick").setup()
    require("mini.surround").setup()
  end
}
