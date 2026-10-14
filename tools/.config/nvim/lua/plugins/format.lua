return {
	-- {
	-- 	"nmac427/guess-indent.nvim",
	-- 	config = function()
	-- 		require("guess-indent").setup({})
	-- 	end,
	-- },
	{
		"stevearc/conform.nvim",
		opts = {},
		config = function()
			local conform = require("conform")

			conform.setup({
				formatters_by_ft = {
					lua = { "stylua" },
					toml = { "tombi" },
					json = { "prettier" },
          css = { "prettier" },
          -- java = { "google-java-format" },
          java = { "clang-format" },
					["_"] = { "biome-check", "prettier", stop_after_first = true },
				},
				formatters = {
					["tailwind-class-sorter"] = {
						command = "biome",
						args = { "lint", "$FILENAME", "--only=lint/nursery/useSortedClasses", "--write", "--unsafe" },
						stdin = false,
					},
          ["google-java-format"] = {
            prepend = { "--aosp" },
          }
				},
			})

			vim.keymap.set({ "n", "v" }, "<leader>p", function()
				conform.format({
					lsp_format = "fallback",
					async = true,
				})
			end, { desc = "Format file" })

			vim.keymap.set("n", "<leader>P", function()
				conform.format({
					formatters = { "tailwind-class-sorter" },
					lsp_format = "never",
					async = false,
				})
			end, { desc = "Sort Tailwind classes" })
		end,
	},
}
