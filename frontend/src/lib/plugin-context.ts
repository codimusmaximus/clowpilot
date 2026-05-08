import type { PluginStatus } from "./types";

export type PluginContextCommand = {
  id: string;
  label: string;
  description: string;
  icon: "Plug" | "Wrench";
};

export function formatPluginToolName(name: string) {
  return name.replaceAll("_", " ");
}

export function createPluginContextCommands(
  plugins: PluginStatus[]
): PluginContextCommand[] {
  const commands: PluginContextCommand[] = [];
  for (const plugin of plugins) {
    commands.push({
      id: `plugin-${plugin.id.replaceAll(".", "-")}`,
      label: `/plugin ${plugin.id}`,
      description: `Add ${plugin.name} plugin context`,
      icon: "Plug",
    });
    for (const tool of plugin.tools) {
      commands.push({
        id: `tool-${tool.replaceAll("_", "-")}`,
        label: `/tool ${tool}`,
        description: `Add ${formatPluginToolName(tool)} tool context`,
        icon: "Wrench",
      });
    }
  }
  return commands;
}
