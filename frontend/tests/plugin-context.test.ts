import { describe, expect, it } from "vitest";
import {
  createPluginContextCommands,
  formatPluginToolName,
} from "../src/lib/plugin-context";
import type { PluginStatus } from "../src/lib/types";

const workspacePlugin: PluginStatus = {
  id: "core.workspace",
  name: "Workspace",
  type: "core",
  enabled: true,
  config: {},
  configSchema: null,
  tools: ["list_tree", "read_file", "replace_file_lines"],
};

describe("plugin context commands", () => {
  it("formats tool names for readable command descriptions", () => {
    expect(formatPluginToolName("replace_file_lines")).toBe(
      "replace file lines"
    );
  });

  it("creates one plugin command plus one command per exposed tool", () => {
    const commands = createPluginContextCommands([workspacePlugin]);

    expect(commands).toHaveLength(4);
    expect(commands[0]).toEqual({
      id: "plugin-core-workspace",
      label: "/plugin core.workspace",
      description: "Add Workspace plugin context",
      icon: "Plug",
    });
    expect(commands.slice(1).map((command) => command.label)).toEqual([
      "/tool list_tree",
      "/tool read_file",
      "/tool replace_file_lines",
    ]);
  });

  it("keeps command ids stable and slash-safe", () => {
    const commands = createPluginContextCommands([workspacePlugin]);

    expect(commands.map((command) => command.id)).toEqual([
      "plugin-core-workspace",
      "tool-list-tree",
      "tool-read-file",
      "tool-replace-file-lines",
    ]);
  });
});
