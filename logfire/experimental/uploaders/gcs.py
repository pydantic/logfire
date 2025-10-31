from io import BytesIO

from google.cloud import storage

from logfire.experimental.uploaders import BaseUploader, UploadItem


class GcsUploader(BaseUploader):
    """Google Cloud Storage uploader."""

    def __init__(self, bucket_name: str):
        self.bucket_name = bucket_name
        self.storage_client = storage.Client()
        self.bucket: storage.Bucket = self.storage_client.bucket(bucket_name)  # pyright: ignore [reportUnknownMemberType]

    def upload(self, item: UploadItem):
        """Upload the given item to GCS."""
        blob: storage.Blob = self.bucket.blob(item.key)  # pyright: ignore [reportUnknownMemberType]
        blob.upload_from_file(BytesIO(item.value), content_type=item.media_type)  # pyright: ignore [reportUnknownMemberType]

    def get_attribute_value(self, key: str):
        """Return the GCS authenticated URL for the uploaded item."""
        return f'https://storage.cloud.google.com/{self.bucket_name}/{key}'
