from github import Github

from buildbot.plugins import *

EXCLUDE = {
    'lexibank': [
        'pylexibank',
        'lexibank',
        'phylogenetics-data-management-tutorial',
        'template',
    ],
    'cldf-datasets': [
        'cldf-datasets',
    ]
}


class Dataset:
    def __init__(self, org, url):
        self.url = url
        self.org = org
        self.name = url.split("/")[-1].replace(".git", "")

    @property
    def id(self):
        return '{0.org}-{0.name}'.format(self)

    @property
    def schedulers(self):
        return [schedulers.ForceScheduler(name="%s-force" % self.id, builderNames=[self.id])]

    @property
    def builder(self):
        factory = util.BuildFactory()
        # check out the source
        factory.addStep(steps.Git(repourl=self.url, mode='full', method="fresh"))

        # install and upgrade
        factory.addStep(
            steps.ShellCommand(
                command=["pip", "install", "--upgrade", "."],
                workdir="build",
                env={"PYTHONPATH": "."},
                name="install dataset"
            )
        )
        factory.addStep(
            steps.ShellCommand(
                command=["pip", "install", "--upgrade", "pytest", "pytest-cldf"],
                workdir="build",
                env={"PYTHONPATH": "."},
                name="install tools"
            )
        )

        # make cldf
        cmd = 'lexibank.makecldf' if self.org == 'lexibank' else 'makecldf'
        # TODO.. need glottolog and concepticon
        # cldfbench lexibank.makecldf --glottolog-version v4.1 --concepticon-version v2.2.1 "${1}"
        #factory.addStep(
        #    steps.ShellCommand(
        #        command=["cldfbench", "lexibank.makecldf", "cldf/cldf-metadata.json"],
        #        workdir="build",
        #        env={"PYTHONPATH": "."},
        #        name="validate"
        #    )
        #)

        # validate
        mdname = 'cldf-metadata.json' if self.org == 'lexibank' else ''
        if mdname:
            factory.addStep(
                steps.ShellCommand(
                    command=["cldf", "validate", "cldf/{0}".format(mdname)],
                    workdir="build",
                    env={"PYTHONPATH": "."},
                    name="validate"
                )
            )
        # run tests
        factory.addStep(
            steps.ShellCommand(
                command=["pytest"], workdir="build",
                env={"PYTHONPATH": "."},
                name="pytest"
            )
        )

        if self.org == 'lexibank':
            # run checkss
            factory.addStep(
                steps.ShellCommand(
                    command=["cldfbench", "--log-level", "WARN", "lexibank.check", self.name],
                    workdir="build",
                    env={"PYTHONPATH": "."},
                    name="lexicheck"
                )
            )
        return factory


def iter_datasets():
    gh = Github()
    for org, exclude in EXCLUDE.items():
        for repo in gh.get_organization(org).get_repos():
            dataset = Dataset(org, repo.clone_url)
            if dataset.name not in exclude:
                # FIXME: for dev
                if dataset.name in ['birchallchapacuran', 'dryerorder']:
                    yield Dataset(org, repo.clone_url)


DATASETS = sorted(iter_datasets(), key=lambda ds: (ds.org, ds.name))


# This is the dictionary that the buildmaster pays attention to. We also use
# a shorter alias to save typing.
c = BuildmasterConfig = {}
c['buildbotNetUsageData'] = None

####### WORKERS

# The 'workers' list defines the set of recognized workers. Each element is
# a Worker object, specifying a unique worker name and password.  The same
# worker name and password must be configured on the worker.
c['workers'] = [worker.Worker("worker", "pass")]

# 'protocols' contains information about protocols which master will use for
# communicating with workers. You must define at least 'port' option that workers
# could connect to your master with this protocol.
# 'port' must match the value configured into the workers (with their
# --master option)
c['protocols'] = {'pb': {'port': 9989}}

####### CHANGESOURCES

# the 'change_source' setting tells the buildmaster how it should find out
# about source code changes.  Here we point to the buildbot version of a python hello-world project.

c['change_source'] = []
#    changes.GitPoller(
#        repo,
#        workdir='workdir.%s' % name,
#        branch='master',
#        pollInterval=300
#   ) for name, repo in repos.items()]

####### SCHEDULERS

# Configure the Schedulers, which decide how to react to incoming changes.
c['schedulers'] = [
    schedulers.Triggerable(name="release", builderNames=[ds.id for ds in DATASETS]),
    schedulers.ForceScheduler(name="release-force", builderNames=['release'])
]
for ds in DATASETS:
    c['schedulers'].extend(ds.schedulers)


####### BUILDERS

# The 'builders' list defines the Builders, which tell Buildbot how to perform a build:
# what steps, and which workers can execute them.  Note that any particular build will
# only take place on one worker.

release = util.BuildFactory()
release.addStep(steps.Trigger(schedulerNames=['release'], waitForFinish=False))
c['builders'] = [util.BuilderConfig(name='release', workernames=["worker"], factory=release)]

for ds in DATASETS:
    c['builders'].append(util.BuilderConfig(name=ds.id, workernames=["worker"], factory=ds.builder))

####### BUILDBOT SERVICES

# 'services' is a list of BuildbotService items like reporter targets. The
# status of each build will be pushed to these targets. buildbot/reporters/*.py
# has a variety to choose from, like IRC bots.

c['services'] = []

####### PROJECT IDENTITY

# the 'title' string will appear at the top of this buildbot installation's
# home pages (linked to the 'titleURL').

c['title'] = "CLDF Buildbot"
c['titleURL'] = "https://lexibot.github.io/"

# the 'buildbotURL' string should point to the location where the buildbot's
# internal web server is visible. This typically uses the port number set in
# the 'www' entry below, but with an externally-visible host name which the
# buildbot cannot figure out without some help.

c['buildbotURL'] = "http://localhost:8010/"

# minimalistic config to activate new web UI
c['www'] = dict(
    port=8010,
    plugins=dict(waterfall_view={}, console_view={}, grid_view={})
)

####### DB URL

c['db'] = {
    # This specifies what database buildbot uses to store its state.
    # It's easy to start with sqlite, but it's recommended to switch to a dedicated
    # database, such as PostgreSQL or MySQL, for use in production environments.
    # http://docs.buildbot.net/current/manual/configuration/global.html#database-specification
    'db_url': "sqlite:///state.sqlite",
}
