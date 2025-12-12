[x] while in the ui and browsing tools  add a button to genereate tests for the selected tool. popup a configuration modal to help them configure how the tests will get generated. it should use the llm to suggest how to genrate tests give some options such as basic, mid, and comprehensive coverage with ability to type in a say "write a test to cover x y z scenario and or update/replace existing ones"
[x] add ability to genreate test for all or selected tools, resources or prompts
[x] improve the request parameter view in mcp explorer in each tool. should look like an ide or better. users like frontend engineers might wanna copy it various formats like json, yaml, whatever is good at that layer, do some research
[x] would it help if our chat/tests maintained some chat history for context and passed back to llm with each call? how does that work best? how should we implement ?
[] for ollama provide better ui tooling to install vairous ollamas and make sure the server for it is running - if we dont have already or if we need, if not ingore this task
[] feature to help optimize the documentation for a tool. press button "optimize" llm docs on a tool and it will experiment with overriding the docs for a tool before sending to llm to a/b test they do and find the best one
[x] in profiles add a button to create the configuration if it doesnt exist insted of showing "Configuration Not Found"
[] support for outh and other auth for mcp
[] make the test page the top page (int he left menu) and the default page when app loads, show a dashboard with graphs and gauges showing test run report for recent and history. keep the dashboard simple and aweasome to lead to way to find the actual tests really easily that should also be folder aware and whatever else you thinks would that feature just viral
[x] have an option  to the curl command in mcp explorer can include the env vars hardcoded
[x] what else would really dazzle frontend engineers and be low cost add feature to mcp explorer?
[x] what is "export schema" label for?
[x] can you also include code snippet for python and maybe one or two other languages showing them calling the mcp tool
[] can you make the cli tool have a dashboard too?
[x] rename mcp explorer to just explorer
[x] a link to documentation on the profile page goes to the preset-io github https://github.com/preset-io/testmcpy/blob/main/docs/MCP_PROFILES.md it should just load the local file if possible or go to origin https://github.com/aminghadersohi/testmcpy/blob/main/docs/MCP_PROFILES.md
[x] replace refs to docs or otherwise links to preset-io github to aminghadersohi
[x] the generated python client code is generic and needs to be specific to the tool and mcp service all hardcoded in there standalone, same as javascript and typescript
[x] change the tab pattern for a drop down selector as there are too many tabs in the code viwer
[x] explorer keeps reloading the page
[] add an mcp service to itself so that while claude code is developing the mcp code it call it and ask to give it the best documentation for a tool and its mcp too would return the best documentation and claude can make a pr for the mcp service code. 
[] in explorer each tool should have a button for generate test, optimize llm docs (the comments on the tool that go to the llm that help it know how to cal the tool) and a button to take the user to chat where it calls the tool for them with default parameters or ideal ones 
[] in the explorer for each tool you should show the tests that are related to it and allow to run them quick and see last result (also history link if possible)

[] ability for any two tools either face same mcp service or different ones but really guaged to benchmark compare the same tool. we need this in cli in the ui 
[] when the ui loads after popping up by running testmcpy serve it shows 0 tools etc sometimes need to reload the page for it to show the tool counts but sometimes it loads. can there be a proper loading indicator that actually works and stops when it loads 
[] add a "debug" button to each tool in explorer that calls the tools with some valid parameters (have it allow the user to override some defaults) and show the trace of the tool call, similar to the ui in auth debug tab

[x] add a feature to smoke test an mcp server by clicking on a button or whtever this type of test is called. it should do the basic things get instance info health check list datasets creaet chart and just maybe run all the tools to see if things all work without errors with reasobnle parameters - DONE: Added `testmcpy smoke-test` CLI command and Smoke Test button in Explorer UI. Tests connection, lists tools, and calls each tool with reasonable parameters. Shows detailed results with success/failure status, duration, and downloadable JSON report. Supports --profile, --mcp-url, --test-all/--basic-only, --max-tools, --format (table/json/summary), and --save options 
[] add feature to regression test an mcp server vs its previous state.
[x] add a feature to geenreate test suite for an mcp service. - DONE: Added `testmcpy generate` command that auto-discovers MCP tools and generates comprehensive test YAML files with discovery, parameter validation, and example tests
[] add another mcp service or more to the profiles (context87, etc)
[] can we get chat to be realtime char by char like claude itself? rn it says thinking for a while
[x] can the chat render md responses - DONE: Added react-markdown with GitHub Flavored Markdown support, custom dark theme styling, inline code highlighting, code blocks with borders, clickable links that open in new tabs
[x] `testmcpy config-mcp claude-desktop` has error "Error: No authentication token available Provide --token or configure dynamic JWT (MCP_AUTH_API_*)" can it take the default settings from mcp_services.yaml and set that up? - FIXED: Now reads auth from MCP profile first (bearer, jwt, none), falls back to env vars, shows helpful error with 3 options if no auth available 

