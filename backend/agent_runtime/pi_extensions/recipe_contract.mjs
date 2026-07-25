/**
 * The only tool exposed to the first Pi sidecar integration.
 *
 * It deliberately has no filesystem, process, network, project-write, or
 * renderer access. VideoForge loads and persists Lab recipes itself; Pi can
 * use this tool only to restate that handoff contract during a director turn.
 */
export default function registerVideoForgeRecipeContract(pi) {
  pi.registerTool({
    name: "videoforge_recipe_contract",
    label: "VideoForge recipe contract",
    description: "Describe the approved VideoForge recipe handoff. It does not read or change project files.",
    parameters: {
      type: "object",
      properties: {
        recipeId: { type: "string", description: "The VideoForge recipe already selected by the Director." },
      },
      required: ["recipeId"],
      additionalProperties: false,
    },
    async execute(_toolCallId, params) {
      return {
        content: [{ type: "text", text: `Recipe ${params.recipeId} is owned by VideoForge Lab RunStore; Pi may propose actions but cannot write project data or delivery artifacts.` }],
        details: {
          recipeId: params.recipeId,
          permissions: ["describe_recipe_contract"],
          denied: ["filesystem", "project_write", "jianying_write", "network", "process"],
        },
      };
    },
  });
}
