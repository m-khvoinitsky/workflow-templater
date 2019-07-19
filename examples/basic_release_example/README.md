Suppose you have some workflow of a recurring event like releasing new version of some software by your company which requires coordinated work from several people. Suppose you have following structure (very simplified) of Jira issues for each release:

* Main issue with summary
    * Prepare client build
    * Release client (blocked by "Prepare client build")
    * Release server-side code
    * Testing (blocked by "Release server-side code")
* Email notification wich states something like: "On this date at that time we're going to release new shiny version of our software. Release task: https://jira.example.com/browse/PRJ-1234"

See the files in this folder for example implementation of this template.
