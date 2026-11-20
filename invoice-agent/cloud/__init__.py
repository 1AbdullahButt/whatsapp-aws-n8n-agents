"""AWS version of the extraction step (milestone B4).

    PDF uploaded to S3 (inbox bucket)
      -> S3 event notification -> SQS queue (3 tries, then dead-letter queue)
      -> worker Lambda (extract_worker.py): same pdfplumber extractor as B1
      -> one item per invoice in DynamoDB, plus a duplicate-key item

No Textract: it is not on the AWS Free plan, and the local extractor is pure Python.
"""
