"""
    Most bluesky-kafka tests require a Kafka broker.

    Start Kafka and Zookeeper like this:
      $ cd scripts
      $ bash start_kafka.sh
    Stop Kafka and Zookeeper with Ctrl-C.
    Remove Kafka and Zookeeper containers like this:
      $ sudo docker ps -a -q
      78485383ca6f
      8a80fb4a385f
      $ sudo docker stop 78485383ca6f 8a80fb4a385f
      78485383ca6f
      8a80fb4a385f
      $ sudo docker rm 78485383ca6f 8a80fb4a385f
      78485383ca6f
      8a80fb4a385f
    Or remove ALL containers like this:
      $ sudo docker stop $(sudo docker ps -a -q)
      $ sudo docker rm $(sudo docker ps -a -q)
    Use this in difficult cases to remove *all traces* of docker containers:
      $ sudo docker system prune -a
"""
import pickle

import msgpack
import numpy as np
import pytest

from event_model import sanitize_doc


@pytest.mark.parametrize(
    "serializer, deserializer",
    [(pickle.dumps, pickle.loads), (msgpack.packb, msgpack.unpackb)],
)
def test_basic_producer_and_basic_consumer(
    temporary_topics,
    basic_producer_factory,
    consume_kafka_messages,
    serializer,
    deserializer,
):
    """Test producing and consuming Kafka messages.

    Messages will be produced by two `bluesky_kafka.produce.BasicProducers`.
    Messages will be consumed by a `bluesky_kafka.consume.BasicConsumer`.

    Parameters
    ----------
    temporary_topics: context manager (pytest fixture)
        creates and cleans up temporary Kafka topics for testing
    publisher_factory: pytest fixture
        fixture-as-a-factory for creating Publishers
    serializer: function (pytest parameter)
        function used to serialize Kafka messages
    deserializer: function (pytest parameter)
        function used to deserialize Kafka messages
    """

    with temporary_topics(
        topics=[
            f"a.test.basic.publisher.and.basic.consumer.{serializer.__module__}",
            f"b.test.basic.publisher.and.basic.consumer.{serializer.__module__}",
        ]
    ) as topics:
        failed_deliveries = []
        successful_deliveries = []

        def on_delivery(err, msg):
            if err is None:
                successful_deliveries.append(msg)
            else:
                failed_deliveries.append((err, msg))

        basic_producer_0 = basic_producer_factory(
            topic=topics[0],
            key=f"{topics[0]}.producer.key",
            on_delivery=on_delivery,
            serializer=serializer,
        )

        basic_producer_1 = basic_producer_factory(
            topic=topics[1],
            key=f"{topics[1]}.producer.key",
            on_delivery=on_delivery,
            serializer=serializer,
        )

        # test numpy serialization
        messages = [
            {
                "numpy_data": {"nested": np.array([x, x + 1, x + 2])},
                "numpy_scalar": np.float64(x),
                "numpy_array": np.ones((x, x)),
            }
            for x in [1, 2, 3, 4]
        ]

        produced_messages = []
        for basic_producer in (basic_producer_0, basic_producer_1):
            for message in messages:
                basic_producer.produce(message)
                produced_messages.append(message)
            basic_producer.flush()

        # expect 8 successful deliveries and 0 failed deliveries
        assert len(successful_deliveries) == 8
        assert len(failed_deliveries) == 0

        # consume the messages
        consumed_messages, consumer = consume_kafka_messages(
            expected_message_count=len(messages),
            kafka_topics=topics,
            deserializer=deserializer,
        )

        assert len(messages) == len(consumed_messages)
        assert consumer.closed

        # sanitize_doc normalizes some data, such as numpy arrays, that are
        # problematic for direct comparison of messages
        sanitized_messages = [sanitize_doc(message) for message in messages]
        sanitized_consumed_messages = [
            sanitize_doc(message) for message in consumed_messages
        ]

        assert len(sanitized_consumed_messages) == len(sanitized_messages)
        assert sanitized_consumed_messages == sanitized_messages
