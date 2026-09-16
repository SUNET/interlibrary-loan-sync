export PROCRASTINATE_APP=jobs.app.app

or give it directly

secretspec run -- procrastinate --app=jobs.app.app schema --apply
secretspec run -- procrastinate --app=jobs.app.app healthchecks

procrastinate --app=ill_bridge.jobs.app.app shell list_jobs
procrastinate --app=ill_bridge.jobs.app.app shell list_queues
procrastinate --app=ill_bridge.jobs.app.app healthchecks
