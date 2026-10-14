return {
	"echasnovski/mini.nvim",
	version = false, -- main branch
	dependencies = {
		"JoosepAlviste/nvim-ts-context-commentstring",
	},
	config = function()
		require("mini.diff").setup()
		vim.keymap.set("n", "<leader>gd", function()
			local buffer = vim.api.nvim_get_current_buf()
			MiniDiff.toggle_overlay(buffer)
		end, { desc = "Open diff view" })
		require("mini.basics").setup({
			options = {
				basic = true,
				extra_ui = false,
			},
			mappings = {
				basic = true,
				windows = true,
				move_with_alt = true,
			},
			autocommands = {
				basic = true,
				relnum_in_visual_mode = true,
			},
		})
		require("mini.bracketed").setup()
		require("mini.pairs").setup()
		require("mini.pick").setup()
		require("mini.surround").setup()
		require("mini.indentscope").setup()
		require("mini.cursorword").setup({
			delay = 0,
		})

		require("ts_context_commentstring").setup({
			enable_autocmd = false,
		})
		require("mini.comment").setup({
			options = {
				custom_commentstring = function()
					local ok, commentstring = pcall(require("ts_context_commentstring").calculate_commentstring)

					if ok and commentstring then
						return commentstring
					end

					return vim.bo.commentstring
				end,
			},
		})
	end,
}
