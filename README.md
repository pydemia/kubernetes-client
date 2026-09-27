# kubernetes-client

High-level functional API for Kubernetes Resources and 3rd party CRDs,
based on the official kubernetes-client, and more.

The 0.1.8 package was restored from its PyPI wheel in commit `f5e691b`.
The current source version is 0.9.0. It supports Python 3.10 through 3.14.
Its public import is `from kubernetes_client import KubernetesManager`.
The tests pass with the stable `kubernetes` 36.0.3 client and the
37.0.0b1 prerelease for Kubernetes 1.37.

Run the tests with `python -m unittest discover -s tests` and build the
package with `python -m build`. The compatibility tests use Kubernetes
model objects and mocked API calls; they do not test a live cluster.

Publish a release by running the `Publish to PyPI` GitHub Actions workflow
with its Git tag, such as `v0.9.0`. The tag must match the package version.
PyPI Trusted Publishing authorizes `publish.yml` in this repository with
the `pypi` GitHub Actions environment.

The build configuration originated from the 0.1.0 source distribution and
the 0.1.8 wheel metadata. See [RECOVERY.md](RECOVERY.md) for the source and
limits of the initial recovery.
