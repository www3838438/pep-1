""" Tests for PipelineInterface ADT. """

import copy
import inspect
import itertools
import logging
import os
import random
import sys
if sys.version_info < (3, 3):
    from collections import Iterable, Mapping
else:
    from collections.abc import Iterable, Mapping

import mock
import pytest
import yaml

from looper.models import \
    PipelineInterface, Sample, _InvalidResourceSpecificationException, \
    _MissingPipelineConfigurationException, DEFAULT_COMPUTE_RESOURCES_NAME


__author__ = "Vince Reuter"
__email__ = "vreuter@virginia.edu"


_LOGGER = logging.getLogger(__name__)


# Values with which to build pipeline interface keys and names
PIPELINE_NAMES = ["ATACseq", "WGBS"]
EXTENSIONS = [".py", ".sh", ".R"]

# Compute resource bundles for pipeline interface configuration data
DEFAULT_RESOURCES = {"file_size": 0, "cores": 1, "mem": 8000,
                     "time": "0-01:00:00", "partition": "local"}
MIDSIZE_RESOURCES = {"file_size": 10, "cores": 8, "mem": 16000,
                     "time": "0-07:00:00", "partition": "serial"}
HUGE_RESOURCES = {"file_size": 30, "cores": 24, "mem": 64000,
                  "time": "30-00:00:00", "partition": "longq"}
HUGE_RESOURCES_NAME = "huge"



def pytest_generate_tests(metafunc):
    """ Customization specific to test cases in this module. """
    try:
        parameters = metafunc.cls.PARAMETERS
    except AttributeError:
        _LOGGER.debug("No indirect parameterization for test class: '{}'".
                      format(metafunc.cls))
        pass
    else:
        for name, values in parameters.items():
            metafunc.parametrize(argnames=name, argvalues=values)
    if metafunc.cls == ConstructorPathParsingTests:
        # Provide test case with two PipelineInterface config bundles.
        metafunc.parametrize(
                argnames="piface_config_bundles",
                argvalues=[(atacseq_iface_without_resources(),
                            {"name": "sans-path"})])



@pytest.fixture(scope="function")
def basic_pipe_iface_data(request):
    """ Minimal PipelineInterface configuration data. """
    extension = request.getfixturevalue("extension") \
            if "extension" in request.fixturenames else ".py"
    return {pipe_name + extension: {"name": pipe_name}
            for pipe_name in PIPELINE_NAMES}



@pytest.fixture(scope="function")
def resources():
    """ Basic PipelineInterface compute resources data. """
    return {DEFAULT_COMPUTE_RESOURCES_NAME: copy.deepcopy(DEFAULT_RESOURCES),
            "huge": copy.copy(HUGE_RESOURCES)}



@pytest.fixture(scope="function")
def pi_with_resources(request, basic_pipe_iface_data, resources):
    """ Add resource bundle data to each config section. """
    if "use_new_file_size" in request.fixturenames:
        file_size_name = "min_file_size" if \
                request.getfixturevalue("use_new_file_size") else "file_size"
        for rp_data in resources.values():
            size1 = rp_data.pop("file_size", None)
            size2 = rp_data.pop("min_file_size", None)
            size = size1 or size2
            if size:
                rp_data[file_size_name] = size
    pipe_iface_config = PipelineInterface(basic_pipe_iface_data)
    for pipe_data in pipe_iface_config.pipelines:
        pipe_data["resources"] = resources
    return pipe_iface_config



@pytest.mark.parametrize(argnames="from_file", argvalues=[False, True])
def test_constructor_input_types(tmpdir, from_file, basic_pipe_iface_data):
    """ PipelineInterface constructor handles Mapping or filepath. """
    if from_file:
        pipe_iface_config = tmpdir.join("pipe-iface-conf.yaml").strpath
        with open(tmpdir.join("pipe-iface-conf.yaml").strpath, 'w') as f:
            yaml.safe_dump(basic_pipe_iface_data, f)
    else:
        pipe_iface_config = basic_pipe_iface_data
    pi = PipelineInterface(pipe_iface_config)
    assert basic_pipe_iface_data == pi.pipe_iface_config
    assert pi.pipe_iface_file == (pipe_iface_config if from_file else None)



@pytest.mark.parametrize(
        argnames="funcname_and_kwargs",
        argvalues=[("choose_resource_package", {"file_size": 4}),
                   ("get_arg_string",
                    {"sample": Sample(
                            {"sample_name": "arbitrary-sample-name"})}),
                   ("get_attribute",
                    {"attribute_key": "irrelevant-attr-name"}),
                   ("get_pipeline_name", {}),
                   ("uses_looper_args", {})])
@pytest.mark.parametrize(argnames="use_resources", argvalues=[False, True])
def test_unconfigured_pipeline_exception(
        funcname_and_kwargs, use_resources, pi_with_resources):
    """ Each public function throws same exception given unmapped pipeline. """
    pi = pi_with_resources
    if not use_resources:
        for pipeline in pi.pipelines:
            try:
                del pipeline["resources"][DEFAULT_COMPUTE_RESOURCES_NAME]
            except KeyError:
                # Already no default resource package.
                pass

    # Each of the functions being tested should take pipeline_name arg,
    # and we want to test behavior for the call on an unknown pipeline.
    funcname, kwargs = funcname_and_kwargs
    func = getattr(pi, funcname)
    required_parameters = inspect.getargspec(func).args
    for parameter in ["pipeline_name", "pipeline"]:
        if parameter in required_parameters and parameter not in kwargs:
            kwargs[parameter] = "missing-pipeline"
    with pytest.raises(_MissingPipelineConfigurationException):
        func.__call__(**kwargs)



class PipelineInterfaceNameResolutionTests:
    """ Name is explicit or inferred from key. """


    @pytest.mark.parametrize(
            argnames="name_and_ext_pairs",
            argvalues=itertools.combinations(
                    itertools.product(PIPELINE_NAMES, EXTENSIONS), 2))
    def test_get_pipeline_name_explicit(self, name_and_ext_pairs):
        """ Configuration can directly specify pipeline name. """
        names, extensions = zip(*name_and_ext_pairs)
        pipelines = [name + ext for name, ext in name_and_ext_pairs]
        pi_conf_data = {pipeline: {"name": name}
                        for pipeline, name in zip(pipelines, names)}
        pi = PipelineInterface(pi_conf_data)
        for pipeline, expected_name in zip(pipelines, names):
            assert expected_name == pi.get_pipeline_name(pipeline)


    def test_get_pipeline_name_inferred(self):
        """ Script implies pipeline name if it's not explicitly configured. """
        pipeline_names = ["wgbs", "atacseq"]
        for extensions in itertools.combinations(EXTENSIONS, 2):
            pipelines = [name + ext for name, ext
                         in zip(pipeline_names, extensions)]
            pi_config_data = {pipeline: None for pipeline in pipelines}
            with mock.patch("looper.models.PipelineInterface._expand_paths"):
                pi = PipelineInterface(pi_config_data)
            for expected_name, pipeline in zip(pipeline_names, pipelines):
                assert expected_name == pi.get_pipeline_name(pipeline)



class PipelineInterfaceResourcePackageTests:
    """ Tests for pipeline's specification of compute resources. """

    PARAMETERS = {"use_new_file_size": [False, True]}


    def test_requires_default(
            self, use_new_file_size, pi_with_resources):
        """ If provided, resources specification needs 'default.' """
        pi = pi_with_resources
        for name, pipeline in pi:
            try:
                del pipeline["resources"][DEFAULT_COMPUTE_RESOURCES_NAME]
            except KeyError:
                # Already no default resource package.
                pass
            assert "default" not in pipeline["resources"]
            with pytest.raises(_InvalidResourceSpecificationException):
                pi.choose_resource_package(
                        name, file_size=HUGE_RESOURCES["file_size"] + 1)


    def test_negative_file_size_request(
            self, use_new_file_size, pi_with_resources):
        """ Negative file size is prohibited. """
        pi = pi_with_resources
        for pipeline_name in pi.pipeline_names:
            negative_file_size = -10 * random.random()
            with pytest.raises(ValueError):
                pi.choose_resource_package(
                        pipeline_name, file_size=negative_file_size)


    @pytest.mark.parametrize(argnames="file_size", argvalues=[0, 10, 101])
    def test_resources_not_required(
            self, use_new_file_size, file_size, pi_with_resources):
        """ Compute resource specification is optional. """
        pi = pi_with_resources
        for pipe_data in pi.pipelines:
            del pipe_data["resources"]
        for pipe_name in pi.pipeline_names:
            assert {} == pi.choose_resource_package(pipe_name, int(file_size))
            assert {} == pi.choose_resource_package(pipe_name, float(file_size))


    @pytest.mark.parametrize(
            argnames=["file_size", "expected_package_name"],
            argvalues=[(0, "default"), (4, "default"),
                       (16, "midsize"), (64, "huge")])
    def test_selects_proper_resource_package(
            self, use_new_file_size, pi_with_resources,
            file_size, expected_package_name):
        """ Minimal resource package sufficient for pipeline and file size. """
        for pipe_data in pi_with_resources.pipelines:
            pipe_data["resources"].update(
                    {"midsize": copy.deepcopy(MIDSIZE_RESOURCES)})
        for pipe_name, pipe_data in pi_with_resources:
            observed_package = pi_with_resources.choose_resource_package(
                pipe_name, file_size)
            expected_package = copy.deepcopy(
                    pipe_data["resources"][expected_package_name])
            assert expected_package == observed_package


    def test_negative_file_size_prohibited(
            self, use_new_file_size, pi_with_resources):
        """ Negative min file size in resource package spec is prohibited. """
        file_size_attr = "min_file_size" if use_new_file_size else "file_size"
        for pipe_data in pi_with_resources.pipelines:
            for package_data in pipe_data["resources"].values():
                package_data[file_size_attr] = -5 * random.random()
        for pipe_name in pi_with_resources.pipeline_names:
            file_size_request = random.randrange(1, 11)
            with pytest.raises(ValueError):
                pi_with_resources.choose_resource_package(
                        pipe_name, file_size_request)


    def test_file_size_spec_not_required_for_default(
            self, use_new_file_size, basic_pipe_iface_data):
        """ Default package implies minimum file size of zero. """

        def clear_file_size(resource_package):
            for fs_var_name in ("file_size", "min_file_size"):
                if fs_var_name in resource_package:
                    del resource_package[fs_var_name]

        # Create the resource package specification data.
        resources_data = dict(zip(
                ["default", "midsize", "huge"],
                [copy.deepcopy(data) for data in
                 [DEFAULT_RESOURCES, MIDSIZE_RESOURCES, HUGE_RESOURCES]]))
        for pack_name, pack_data in resources_data.items():
            # Use file size spec name as appropriate; clean default package.
            if pack_name == "default":
                clear_file_size(pack_data)
            elif use_new_file_size:
                pack_data["min_file_size"] = pack_data.pop("file_size")

        # Add resource package spec data and create PipelineInterface.
        pipe_iface_data = copy.deepcopy(basic_pipe_iface_data)
        for pipe_data in pipe_iface_data.values():
            pipe_data["resources"] = resources_data
        pi = PipelineInterface(pipe_iface_data)

        # We should always get default resource package for mini file.
        for pipe_name, pipe_data in pi:
            default_resource_package = \
                    pipe_data["resources"][DEFAULT_COMPUTE_RESOURCES_NAME]
            clear_file_size(default_resource_package)
            assert default_resource_package == \
                   pi.choose_resource_package(pipe_name, 0.001)


    @pytest.mark.parametrize(
            argnames="min_file_size", argvalues=[-1, 1])
    def test_default_package_new_name_zero_size(
            self, use_new_file_size, min_file_size, pi_with_resources):
        """ Default resource package sets minimum file size to zero. """

        for pipe_name, pipe_data in pi_with_resources:
            # Establish faulty default package setting for file size.
            default_resource_package = pipe_data["resources"]["default"]
            if use_new_file_size:
                if "file_size" in default_resource_package:
                    del default_resource_package["file_size"]
                default_resource_package["min_file_size"] = min_file_size
            else:
                if "min_file_size" in default_resource_package:
                    del default_resource_package["min_file_size"]
                default_resource_package["file_size"] = min_file_size

            # Get the resource package to validate.
            # Requesting file size of 0 should always trigger default package.
            observed_resource_package = \
                    pi_with_resources.choose_resource_package(pipe_name, 0)

            # Default package is an early adopter of the new file size name.
            expected_resource_package = copy.deepcopy(default_resource_package)
            if "file_size" in expected_resource_package:
                del expected_resource_package["file_size"]
            # Default packages forces its file size value to 0.
            expected_resource_package["min_file_size"] = 0

            assert expected_resource_package == observed_resource_package


    def test_file_size_spec_required_for_non_default_packages(
            self, use_new_file_size, basic_pipe_iface_data):
        """ Resource packages besides default require file size. """

        # Establish the resource specification.
        resource_package_data = {
                "default": copy.deepcopy(DEFAULT_RESOURCES),
                "huge": copy.deepcopy(HUGE_RESOURCES)}

        # Remove file size for non-default; set it for default.
        del resource_package_data["huge"]["file_size"]
        if use_new_file_size:
            resource_package_data["default"]["min_file_size"] = \
                    resource_package_data["default"].pop("file_size")

        # Create the PipelineInterface.
        for pipe_data in basic_pipe_iface_data.values():
            pipe_data["resources"] = resource_package_data
        pi = PipelineInterface(basic_pipe_iface_data)

        # Attempt to select resource package should fail for each pipeline,
        # regardless of the file size specification; restrict to nonnegative
        # file size requests to avoid collision with ValueError that should
        # arise if requesting resource package for a negative file size value.
        for pipe_name in pi.pipeline_names:
            with pytest.raises(KeyError):
                pi.choose_resource_package(pipe_name, random.randrange(0, 10))



@pytest.fixture(scope="function")
def atacseq_iface_without_resources():
    """
    Provide the ATAC-Seq pipeline interface as a fixture, without resources.

    Note that this represents the configuration data for the interface for a
    single pipeline. In order to use this in the form that a PipelineInterface
    expects, this needs to be the value to which a key is mapped within a
    larger Mapping.

    :return Mapping: all of the pipeline interface configuration data for
        ATAC-Seq, minus the resources section
    """
    return {
        "name": "ATACseq",
        "looper_args": True,
        "required_input_files": ["read1", "read2"],
        "all_input_files": ["read1", "read2"],
        "ngs_input_files": ["read1", "read2"],
        "arguments": {
            "--sample-name": "sample_name",
            "--genome": "genome",
            "--input": "read1",
            "--input2": "read2",
            "--single-or-paired": "read_type"
        },
        "optional_arguments": {
            "--frip-ref-peaks": "FRIP_ref",
            "--prealignments": "prealignments",
            "--genome-size": "macs_genome_size"
        }
    }



@pytest.fixture(scope="function")
def piface_config_bundles(request, resources):
    """
    Provide the ATAC-Seq pipeline interface as a fixture, including resources.

    Note that this represents the configuration data for the interface for a
    single pipeline. In order to use this in the form that a PipelineInterface
    expects, this needs to be the value to which a key is mapped within a
    larger Mapping.

    :param pytest._pytest.fixtures.SubRequest request: hook into test case
        requesting this fixture, which is queried for a resources value with
        which to override the default if it's present.
    :param Mapping resources: pipeline interface resource specification
    :return Iterable[Mapping]: collection of bundles of pipeline interface
        configuration bundles
    """
    iface_config_datas = request.getfixturevalue("config_bundles")
    if isinstance(iface_config_datas, Mapping):
        data_bundles = iface_config_datas.values()
    elif isinstance(iface_config_datas, Iterable):
        data_bundles = iface_config_datas
    else:
        raise TypeError("Expected mapping or list collection of "
                        "PipelineInterface data: {} ({})".format(
                iface_config_datas, type(iface_config_datas)))
    resources = request.getfixturevalue("resources") \
            if "resources" in request.fixturenames else resources
    for config_bundle in data_bundles:
        config_bundle.update(resources)
    return iface_config_datas



class ConstructorPathParsingTests:
    """ The constructor is responsible for expanding pipeline path(s). """

    ADD_PATH = [True, False]
    PIPELINE_KEYS = ["ATACSeq.py", "no_path.py"]
    RELATIVE_PATH_DATA = [
            ("./arbitrary-test-pipelines",
             {},
             "./arbitrary-test-pipelines"),
            ("path/to/$TEMP_PIPE_LOCS",
             {"TEMP_PIPE_LOCS": "validation-value"},
             "path/to/validation-value")]
    ABSOLUTE_PATHS = [os.path.join("~", "code_home", "bioinformatics"),
                      os.path.join("$TEMP_TEST_HOME", "subfolder"),
                      os.path.join("~", "$TEMPORARY_SUBFOLDER", "leaf")]


    @pytest.fixture(scope="function")
    def pipe_iface_data(self, piface_config_bundles):
        return dict(zip(self.PIPELINE_KEYS, piface_config_bundles))


    @pytest.fixture(scope="function", autouse=True)
    def apply_envvars(self, request):
        """ Use environment variables temporarily. """

        if "envvars" not in request.fixturenames:
            # We're autousing, so check for the relevant fixture.
            return

        original_envvars = {}
        new_envvars = request.getfixturevalue("envvars")

        # Remember values that are replaced as variables are updated.
        for name, value in new_envvars.items():
            try:
                original_envvars[name] = os.environ[name]
            except KeyError:
                pass
            os.environ[name] = value

        def restore():
            # Restore swapped variables and delete added ones.
            for k, v in new_envvars.items():
                try:
                    os.environ[k] = original_envvars[k]
                except KeyError:
                    del os.environ[k]
        request.addfinalizer(restore)


    def test_no_path(self, piface_config_bundles, pipe_iface_data):
        """ PipelineInterface config sections need not specify path. """
        pi = PipelineInterface(pipe_iface_data)
        for pipe_key in self.PIPELINE_KEYS:
            piface_config = pi[pipe_key]
            # Specific negative test of interest.
            assert "path" not in piface_config
            # Positive control validation.
            assert pipe_iface_data[pipe_key] == piface_config


    @pytest.mark.parametrize(
            argnames=["pipe_path", "envvars", "expected"],
            argvalues=RELATIVE_PATH_DATA)
    def test_relative_path(self, piface_config_bundles, pipe_iface_data,
                           pipe_path, envvars, expected, apply_envvars):
        """
        PipelineInterface construction expands pipeline path.

        Environment variable(s) expand(s), but the path remains relative
        if specified as such, deferring the joining with pipelines location
        until used.

        """
        for add_path, pipe_key in zip(self.ADD_PATH, self.PIPELINE_KEYS):
            if add_path:
                pipe_iface_data[pipe_key]["path"] = pipe_path
        pi = PipelineInterface(pipe_iface_data)
        for add_path, pipe_key in zip(self.ADD_PATH, self.PIPELINE_KEYS):
            if add_path:
                assert expected == pi[pipe_key]["path"]
            else:
                assert "path" not in pi[pipe_key]


    @pytest.mark.skip("Not implemented")
    def test_path_expansion(self, piface_config_bundles, pipe_iface_data):
        pass



@pytest.mark.skip("Not implemented")
class PipelineInterfaceArgstringTests:
    """  """
    pass



@pytest.mark.skip("Not implemented")
class PipelineInterfaceLooperArgsTests:
    """  """
    pass
