from io import BytesIO

from google.cloud import storage


class GcsUploader:  # noqa: D101  TODO
    def __init__(self, bucket_name: str):
        self.bucket_name = bucket_name
        self.storage_client = storage.Client()
        self.bucket: storage.Bucket = self.storage_client.bucket(bucket_name)  # pyright: ignore [reportUnknownMemberType]

    def upload(self, key: str, value: bytes, media_type: str):  # noqa: D102  TODO
        blob: storage.Blob = self.bucket.blob(key)  # pyright: ignore [reportUnknownMemberType]
        blob.upload_from_file(BytesIO(value), content_type=media_type)  # pyright: ignore [reportUnknownMemberType]

    def get_attribute_value(self, key: str):  # noqa: D102  TODO
        return f'https://storage.cloud.google.com/{self.bucket_name}/{key}'
