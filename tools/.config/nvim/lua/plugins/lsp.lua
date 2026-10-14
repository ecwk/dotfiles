return {
	{
		"mason-org/mason.nvim",
		opts = {},
	},
	{
		"neovim/nvim-lspconfig",
		config = function()
			vim.lsp.enable("lua_ls")
			vim.lsp.enable("ts_ls")
			vim.lsp.enable("cssls")
			vim.lsp.enable("tailwindcss")
			vim.lsp.config("tailwindcss", {
				settings = {
					experimental = {
						classRegex = {
							"cn\\(([^)]*)\\)", -- cn('p-4 m-2')
							"clsx\\(([^)]*)\\)", -- clsx('flex items-center')
						},
					},
					tailwindCSS = {
						lint = {
							suggestCanonicalClasses = "ignore",
						},
						experimental = {
							classRegex = {
								"cn\\(([^)]*)\\)", -- cn('p-4 m-2')
								"clsx\\(([^)]*)\\)", -- clsx('flex items-center')
							},
						},
					},
				},
			})
			vim.lsp.enable("jdtls")
		end,
	},
	-- {
	-- 	"mason-org/mason-lspconfig.nvim",
	-- 	opts = {},
	-- 	dependencies = {
	-- 		{ "mason-org/mason.nvim", opts = {} },
	-- 		"neovim/nvim-lspconfig",
	-- 	},
	-- },
	-- {
	-- 	"ray-x/lsp_signature.nvim",
	-- 	event = "InsertEnter",
	-- 	enabled = false,
	-- 	opts = {
	-- 		-- toggle_key = "<M-k>",
	-- 		floating_window = false,
	-- 	},
	-- },
}
