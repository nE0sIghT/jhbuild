# jhbuild - a build script for GNOME 1.x and 2.x
# Copyright (C) 2001-2006  James Henstridge
# Copyright (C) 2003-2004  Marco Pesenti Gritti
#
#   mozillamodule.py: rules for building Mozilla
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

__metaclass__ = type

import os

from jhbuild.modtypes import register_module_type, get_dependencies, SkipToState
from jhbuild.modtypes.autotools import AutogenModule
from jhbuild.versioncontrol import cvs
from jhbuild.errors import FatalError, BuildStateError

class MozillaModule(AutogenModule):
    def __init__(self, name, projects, revision, autogenargs='',
		 makeargs='', dependencies=[], after=[], suggests=[],
                 repository = None, extra_env = None):
        AutogenModule.__init__(self, name, branch=None,
                               autogenargs=autogenargs,
                               makeargs=makeargs,
                               dependencies=dependencies,
                               after=after,
                               suggests=suggests,
                               supports_non_srcdir_builds=False,
                               extra_env = extra_env)
        self.repository = repository
        self.revision = revision
	self.projects = projects
	os.environ['MOZ_CO_PROJECT'] = projects

    def get_srcdir(self, buildscript):
        return os.path.join(buildscript.config.checkoutroot, 'mozilla')
    def get_revision(self):
        return self.revision

    def get_mozilla_app(self):
        if self.projects == 'browser':
            return 'firefox'
	elif self.projects == 'xulrunner':
            return 'xulrunner'
        else:
            return 'mozilla'

    def get_mozilla_ver(self, buildscript):
	if self.projects == 'browser':
            filename = os.path.join(self.get_builddir(buildscript),
                                    'browser', 'config', 'version.txt') 
        else:
            filename = os.path.join(self.get_builddir(buildscript),
                                    'config', 'milestone.txt')
	fp = open(filename, 'r')
	for line in fp.readlines():
	    if line[0] not in ('#', '\0', '\n'):
                return line.strip()
        else:
            raise FatalError('could not determine mozilla version')

    def checkout(self, buildscript):
        buildscript.set_action('Checking out', self)
        cmd = ['cvs', '-z3', '-q', '-d', self.repository.cvsroot, 'checkout']
        if self.revision:
            cmd.extend(['-r', self.revision])
        else:
            cmd.append('-A')
        if buildscript.config.sticky_date:
            cmd.extend(['-D', buildscript.config.sticky_date])
        cmd.append('mozilla/client.mk')
        buildscript.execute(cmd, cwd = buildscript.config.checkoutroot)
        
        make = os.environ.get('MAKE', 'make')
        buildscript.execute([make, '-f', 'client.mk', 'checkout'],
                cwd = self.get_builddir(buildscript),
                extra_env = self.extra_env)

    def do_checkout(self, buildscript):
        checkoutdir = self.get_builddir(buildscript)
        client_mk = os.path.join(checkoutdir, 'client.mk')
        if not os.path.exists(client_mk) or \
               cvs.check_sticky_tag(client_mk) != self.revision:
            self.checkout(buildscript)
        else:
            buildscript.set_action('Updating', self)
            make = os.environ.get('MAKE', 'make')
            buildscript.execute([make, '-f', 'client.mk', 'fast-update'],
                    cwd = checkoutdir,
                    extra_env = self.extra_env)

        # did the checkout succeed?
        if not os.path.exists(checkoutdir):
            raise BuildStateError('source directory %s was not created'
                                  % checkoutdir)

        if self.check_build_policy(buildscript):
            raise SkipToState(self.STATE_DONE)
    do_checkout.next_state = AutogenModule.STATE_CONFIGURE
    do_checkout.error_states = [AutogenModule.STATE_FORCE_CHECKOUT]

    def do_force_checkout(self, buildscript):
        self.checkout(buildscript)
    do_force_checkout.next_state = AutogenModule.STATE_CONFIGURE
    do_force_checkout.error_states = [AutogenModule.STATE_FORCE_CHECKOUT]
        
    def do_configure(self, buildscript):
        checkoutdir = self.get_builddir(buildscript)
        buildscript.set_action('Configuring', self)
        if buildscript.config.use_lib64:
            mozilla_path = '%s/lib64/%s-%s' \
                           % (buildscript.config.prefix,
                              self.get_mozilla_app(),
                              self.get_mozilla_ver(buildscript))
        else:
            mozilla_path = '%s/lib/%s-%s' \
                           % (buildscript.config.prefix,
                              self.get_mozilla_app(),
                              self.get_mozilla_ver(buildscript))
        
        cmd = './configure --prefix %s ' % buildscript.config.prefix
        if buildscript.config.use_lib64:
            cmd += " --libdir '${exec_prefix}/lib64'"
        cmd += ' --with-default-mozilla-five-home=%s' % mozilla_path
        cmd += ' %s' % self.autogenargs

        if self.projects:
            cmd += ' --enable-application=%s' % self.projects
        buildscript.execute(cmd, cwd = checkoutdir,
                extra_env = self.extra_env)
    do_configure.next_state = AutogenModule.STATE_BUILD
    do_configure.error_states = [AutogenModule.STATE_FORCE_CHECKOUT]

    def do_install(self, buildscript):
        buildscript.set_action('Installing', self)
        make = os.environ.get('MAKE', 'make')
        cmd = '%s %s %s install' % (make, buildscript.config.makeargs,
                                      self.makeargs)
        buildscript.execute(cmd, cwd = self.get_builddir(buildscript),
                extra_env = self.extra_env)
        nssdir = '%s/include/%s-%s/nss' % (
            buildscript.config.prefix,
            self.get_mozilla_app(),
            self.get_mozilla_ver(buildscript))
        if not os.path.exists(nssdir):
            buildscript.execute(['mkdir', nssdir])

        cmd = ['find', '%s/security/nss/lib/' % self.get_builddir(buildscript),
               '-name', '*.h', '-type', 'f', '-exec', '/bin/cp', '{}',
               '%s/' % nssdir,  ';']
        buildscript.execute(cmd, cwd=self.get_builddir(buildscript))
        buildscript.packagedb.add(self.name, self.get_revision() or '')
    do_install.next_state = AutogenModule.STATE_DONE
    do_install.error_states = []

def parse_mozillamodule(node, config, uri, repositories, default_repo):
    name = node.getAttribute('id')
    projects = node.getAttribute('projects')
    revision = None
    autogenargs = ''
    makeargs = ''
    dependencies = []
    if node.hasAttribute('revision'):
        revision = node.getAttribute('revision')
    if node.hasAttribute('autogenargs'):
        autogenargs = node.getAttribute('autogenargs')
    if node.hasAttribute('makeargs'):
        makeargs = node.getAttribute('makeargs')

    # override revision tag if requested.
    revision = config.branches.get(name, revision)

    autogenargs += ' ' + config.module_autogenargs.get(name, config.autogenargs)
    makeargs += ' ' + config.module_makeargs.get(name, config.makeargs)

    extra_env = config.module_extra_env.get(id)
    dependencies, after, suggests = get_dependencies(node)

    for attrname in ['cvsroot', 'root']:
        if node.hasAttribute(attrname):
            repo = repositories[node.getAttribute(attrname)]
            break
    else:
        repo = repositories.get(default_repo, None)

    return MozillaModule(name, projects, revision, autogenargs, makeargs,
                         dependencies, after, suggests, repo,
                         extra_env = extra_env)

register_module_type('mozillamodule', parse_mozillamodule)
