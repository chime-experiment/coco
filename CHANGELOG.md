### [2020.06.0](https://github.com/chime-experiment/coco/compare/2020.04.0...2020.06.0) (2020-06-11)


### Bug Fixes

* **client:** typo in update-blacklist help text ([a9531f6](https://github.com/chime-experiment/coco/commit/a9531f6dfe7878554c34df45cbded65477b9244b))
* **endpoint:** pass host to metric.get(queue_length) ([53ed20c](https://github.com/chime-experiment/coco/commit/53ed20cb7d097712645905f67e596642ca9b6396)), closes [#194](https://github.com/chime-experiment/coco/issues/194)
* **worker:** ndle redis server timing out ([011678b](https://github.com/chime-experiment/coco/commit/011678be1d299047d16b2521fd3b122c7293f44d)), closes [#203](https://github.com/chime-experiment/coco/issues/203)


### Features

* **cocod:** add option --check-config ([f859728](https://github.com/chime-experiment/coco/commit/f859728e1ff155c62be5c10a40626a86023133bf))
* **master:** add defaults to Master.__init__ arguments ([facb258](https://github.com/chime-experiment/coco/commit/facb258e6dbf16852ab68cec55a593d86ddcdee1))
* **state:** commands to save and load states ([97a0521](https://github.com/chime-experiment/coco/commit/97a05218cefc83c59c256286537773dd1cbbd0eb))


### BREAKING CHANGES

* **state:** The config variable 'storage_path' is not a file anymore, but a
directory. The state is saved there under the name 'active' and saved
states are added here as well. If you are updating your coco instance,
you have to manually move the persistent state from 'storage_path' to
'storage_path'/active.



# Changelog

All notable changes to this project will be documented in this file. See [standard-version](https://github.com/conventional-changelog/standard-version) for commit guidelines.

### [2020.04.0](https://github.com/chime-experiment/coco/compare/2019.12.0...2020.04.0) (2020-04-10)


### Features

* **coco client:** Improve output & show progress ([0315bae](https://github.com/chime-experiment/coco/commit/0315bae)), closes [#186](https://github.com/chime-experiment/coco/issues/186)
* **cocod:** add option --reset ([9a7f9a7](https://github.com/chime-experiment/coco/commit/9a7f9a7)), closes [#184](https://github.com/chime-experiment/coco/issues/184)

## 2019.12.0 (2019-12-09)


### Bug Fixes


* **state:** ignore excluded states if they don't exist ([bc8d8a0](https://github.com/chime-experiment/coco/commit/bc8d8a0))
* **state:** when hashing recurse on list elements ([cbec4df](https://github.com/chime-experiment/coco/commit/cbec4df))

## 2019.11.0 (2019-11-21)


### Bug Fixes

* **master:** disable sanic debug mode ([17c0c08](https://github.com/chime-experiment/coco/commit/17c0c08))


### Features

* **metrics** add metric for tracking how long a request is waiting in the queue ([e2fb5cf](https://github.com/chime-experiment/coco/commit/e2fb5cf))
* **state:** add option: exclude_from_reset ([d9792ec](https://github.com/chime-experiment/coco/commit/d9793ec))


## 2019.10.0 (2019-10-22)


### Bug Fixes

* **request_forwarder:** copy request for coco forwards ([c04fe33](https://github.com/chime-experiment/coco/commit/c04fe33)), closes [#171](https://github.com/chime-experiment/coco/issues/171)
* **slack:** set slack message timeout ([2636da7](https://github.com/chime-experiment/coco/commit/2636da7)), closes [#165](https://github.com/chime-experiment/coco/issues/165)
* **state:** handle errors in _find(path) ([5bcb14c](https://github.com/chime-experiment/coco/commit/5bcb14c))
* **state:** get hash of msgpacked state ([c859d1c](https://github.com/chime-experiment/coco/commit/c859d1c)), closes [kotekan/kotekan#477](https://github.com/kotekan/kotekan/issues/477)
* **worker:** answer with 404 if endpoint unknown ([aaae74a](https://github.com/chime-experiment/coco/commit/aaae74a))


### Features

* **slack:** print error if slack logging failed ([94009a2](https://github.com/chime-experiment/coco/commit/94009a2))
* **state:** make state persistent ([ea36e5a](https://github.com/chime-experiment/coco/commit/ea36e5a)), closes [#85](https://github.com/chime-experiment/coco/issues/85)
