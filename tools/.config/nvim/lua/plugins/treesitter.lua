return {
	"nvim-treesitter/nvim-treesitter",
	lazy = false,
	build = ":TSUpdate",
	config = function()
		local treesitter = require("nvim-treesitter")

		local languages = {
			"html",
			"css",
			"javascript",
			"typescript",
			"jsx",
			"tsx",
			"python",
			"rust",
			"lua",
			"vim",
			"markdown",
			"markdown_inline",
		}

		treesitter.setup()
		treesitter.install(languages)

		vim.api.nvim_create_autocmd("FileType", {
			pattern = languages,
			callback = function()
				vim.treesitter.start()
				-- vim.wo[0][0].foldexpr = "v:lua.vim.treesitter.foldexpr()"
				-- vim.wo[0][0].foldmethod = "expr"
				-- vim.bo.indentexpr = "v:lua.require'nvim-treesitter'.indentexpr()"
			end,
		})
	end,
}
