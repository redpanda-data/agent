validate_file_path = mapping("""
  let file = content().string()
  root.file = if $file.contains("..") {
    throw("invalid file path")
  } else {
    $file
  }
""")

mcp_tool(
  label = "list_files",
  description = "List files in a directory. Use `.` for the current directory.",
  processor = processors(
    attempt(
      validate_file_path,
      command(
        name="ls",
        args_mapping='[["{}", this.file].filepath_join()]'.format(secret("PROJECT_DIR")),
      ),
      mapping("""
      root.files = content().split("\\n")
      if root.files == [""] {
        root = "no files found"
      }
      """)
    ),
    catch(
      mapping(
        """root = ["Directory does not exist"]""",
      )
    ),
  )
)

mcp_tool(
  label = "lint_connect_configuration_file",
  description = "Lint a Connect configuration file, the `value` should be a path to a configuration file.",
  processor = processors(
    attempt(
      validate_file_path,
      command(
        name="rpk",
        args_mapping="""[
            "connect",
            "lint",
            ["{}", this.file].filepath_join(),
          ]""".format(secret("PROJECT_DIR")),
      ),
      mapping('root = "lint success"'),
    ),
    catch(
      mapping("root.error = error()"),
    )
  )
)

mcp_tool(
  label = "ask_docs_agent",
  description = " ".join([
    "Ask the documentation agent for help.",
    "This agent has access to the full documentation for Redpanda.",
    "The `value` should be the question and mention that's it's for Redpanda Connect specifically.",
  ]),
  processor = attempt(
    mapping("""root.query = content().string()"""),
    http(
      verb = "POST",
      url = "https://api.kapa.ai/query/v1/projects/{project_id}/chat/".format(
          project_id=secret("KAPA_PROJECT_ID"),
        ),
      headers = {
        "Content-Type": "application/json",
        "X-API-KEY": secret("KAPA_API_KEY"),
      },
      timeout = "60s",
    )
  )
)
