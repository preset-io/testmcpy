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

