from copy import deepcopy
from typing import Union

import rastervision as rv
from rastervision.core import (Config, ConfigBuilder)
from rastervision.task import TaskConfig
from rastervision.data import (Scene, RasterSourceConfig, LabelSourceConfig,
                               LabelStoreConfig)
from rastervision.protos.scene_pb2 \
    import SceneConfig as SceneConfigMsg

# TODO: Set/save/load AOI


class SceneConfig(Config):
    def __init__(self,
                 scene_id,
                 raster_source,
                 label_source=None,
                 label_store=None,
                 aoi_polygons=None):
        self.scene_id = scene_id
        self.raster_source = raster_source
        self.label_source = label_source
        self.label_store = label_store
        self.aoi_polygons = aoi_polygons

    def create_scene(self, task_config: TaskConfig, tmp_dir: str) -> Scene:
        """Create this scene.

           Args:
              task - TaskConfig
              tmp_dir - Temporary directory to use
        """
        raster_source = self.raster_source.create_source(tmp_dir)
        label_source = None
        if self.label_source:
            label_source = self.label_source.create_source(
                task_config, raster_source.get_extent(),
                raster_source.get_crs_transformer(), tmp_dir)
        label_store = None
        if self.label_store:
            label_store = self.label_store.create_store(
                task_config, raster_source.get_crs_transformer(), tmp_dir)
        return Scene(self.scene_id, raster_source, label_source, label_store,
                     self.aoi_polygons)

    def to_proto(self):
        msg = SceneConfigMsg(
            id=self.scene_id, raster_source=self.raster_source.to_proto())

        if self.label_source:
            msg.ground_truth_label_source.CopyFrom(
                self.label_source.to_proto())
        if self.label_store:
            msg.prediction_label_store.CopyFrom(self.label_store.to_proto())
        return msg

    def to_builder(self):
        return SceneConfigBuilder(self)

    def preprocess_command(self, command_type, experiment_config,
                           context=None):
        if context is None:
            context = []
        context = context + [self]
        io_def = rv.core.CommandIODefinition()

        b = self.to_builder()

        (new_raster_source,
         sub_io_def) = self.raster_source.preprocess_command(
             command_type, experiment_config, context)
        io_def.merge(sub_io_def)
        b = b.with_raster_source(new_raster_source)

        if self.label_source:
            (new_label_source,
             sub_io_def) = self.label_source.preprocess_command(
                 command_type, experiment_config, context)
            io_def.merge(sub_io_def)
            b = b.with_label_source(new_label_source)

        if self.label_store:
            (new_label_store,
             sub_io_def) = self.label_store.preprocess_command(
                 command_type, experiment_config, context)
            io_def.merge(sub_io_def)
            b = b.with_label_store(new_label_store)

        return (b.build(), io_def)

    @staticmethod
    def builder():
        return SceneConfigBuilder()

    @staticmethod
    def from_proto(msg):
        """Creates a SceneConfig from the specificed protobuf message
        """
        return SceneConfigBuilder().from_proto(msg).build()


class SceneConfigBuilder(ConfigBuilder):
    def __init__(self, prev=None):
        config = {}
        if prev:
            config = {
                'scene_id': prev.scene_id,
                'raster_source': prev.raster_source,
                'label_source': prev.label_source,
                'label_store': prev.label_store
            }
        super().__init__(SceneConfig, config)
        self.task = None

    def from_proto(self, msg):
        b = self.with_id(msg.id) \
                .with_raster_source(RasterSourceConfig.from_proto(msg.raster_source))
        if msg.HasField('ground_truth_label_source'):
            b = b.with_label_source(
                LabelSourceConfig.from_proto(msg.ground_truth_label_source))
        if msg.HasField('prediction_label_store'):
            b = b.with_label_store(
                LabelStoreConfig.from_proto(msg.prediction_label_store))

        return b

    def with_task(self, task):
        b = deepcopy(self)
        b.task = task
        return b

    def with_id(self, scene_id):
        b = deepcopy(self)
        b.config['scene_id'] = scene_id
        return b

    def with_raster_source(self,
                           raster_source: Union[str, RasterSourceConfig],
                           channel_order=None):
        """
        Sets the raster source for this scene.

        Args:
           raster_source: Can either be a raster source configuration, or
                          a string. If a string, the registry will be queried
                          to grab the default RasterSourceConfig for the string.
           channel_order: Optional channel order for this raster source.
        """
        b = deepcopy(self)
        if isinstance(raster_source, RasterSourceConfig):
            if channel_order is not None:
                rs = raster_source.to_builder() \
                                  .with_channel_order(channel_order) \
                                  .build()
                b.config['raster_source'] = rs
            else:
                b.config['raster_source'] = raster_source
        else:
            provider = rv._registry.get_default_raster_source_provider(
                raster_source)
            b.config['raster_source'] = provider.construct(
                raster_source, channel_order)

        return b

    def with_label_source(self, label_source: Union[str, LabelSourceConfig]):
        """
        Sets the raster source for this scene.

        Args:
           label_source: Can either be a label source configuration, or
                         a string. If a string, the registry will be queried
                         to grab the default LabelSourceConfig for the string.

        Note:
           A task must be set with `with_task` before calling this, if calling
           with a string.
        """
        b = deepcopy(self)
        if isinstance(label_source, LabelSourceConfig):
            b.config['label_source'] = label_source
        else:
            if not self.task:
                raise rv.ConfigError(
                    "You must set a task with '.with_task' before "
                    'creating a default label store for {}'.format(
                        label_source))
            provider = rv._registry.get_default_label_source_provider(
                self.task.task_type, label_source)
            b.config['label_source'] = provider.construct(label_source)

        return b

    def with_label_store(
            self, label_store: Union[str, LabelStoreConfig, None] = None):
        """
        Sets the raster store for this scene.

        Args:
           label_store: Can either be a label store configuration, or
                        a string, or None. If a string, the registry will
                        be queried to grab the default LabelStoreConfig for
                        the string. If None, then the default for the task
                        from the regsitry will be used.

        Note:
           A task must be set with `with_task` before calling this, if calling
           with a string.
        """
        b = deepcopy(self)
        if isinstance(label_store, LabelStoreConfig):
            b.config['label_store'] = label_store
        elif isinstance(label_store, str):
            if not self.task:
                raise rv.ConfigError(
                    "You must set a task with '.with_task' before "
                    'creating a default label store for {}'.format(
                        label_store))
            provider = rv._registry.get_default_label_store_provider(
                self.task.task_type, label_store)
            b.config['label_store'] = provider.construct(label_store)
        else:
            if not self.task:
                raise rv.ConfigError(
                    "You must set a task with '.with_task' before "
                    'creating a default label store.')
            provider = rv._registry.get_default_label_store_provider(
                self.task.task_type)
            b.config['label_store'] = provider.construct()

        return b
