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
