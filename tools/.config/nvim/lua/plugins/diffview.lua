return {
	"sindrets/diffview.nvim",
	cmd = {
		"DiffviewOpen",
		"DiffviewClose",
		"DiffviewFileHistory",
		"DiffviewToggleFiles",
		"DiffviewFocusFiles",
		"DiffviewRefresh",
	},
	keys = {
		{ "<leader>gv", "<cmd>DiffviewOpen<CR>", desc = "Open Diffview" },
		{ "<leader>gq", "<cmd>DiffviewClose<CR>", desc = "Close Diffview" },
		{ "<leader>gh", "<cmd>DiffviewFileHistory %<CR>", desc = "Current file history" },
		{ "<leader>gH", "<cmd>DiffviewFileHistory<CR>", desc = "Repository history" },
	},
	opts = {},
}
