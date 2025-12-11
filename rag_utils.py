import os
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_qdrant import QdrantVectorStore
from langchain_openai import OpenAIEmbeddings
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

# Global Qdrant client (reused across all operations)
# Similar to how db_conn is global in main.py
_qdrant_client = None

def get_qdrant_client():
    """
    Returns a singleton QdrantClient instance.
    This prevents the "already accessed" error by reusing the same client.
    """
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(path="./qdrant_data")
        print("✅ Qdrant client initialized")
    return _qdrant_client

def load_and_split_document(file_path: str):
    """
    Loads a PDF or Text file and splits it into chunks.
    """
    if file_path.endswith(".pdf"):
        loader = PyPDFLoader(file_path)
    else:
        loader = TextLoader(file_path)

    docs = loader.load()

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        add_start_index=True
    )
    splits = text_splitter.split_documents(docs)
    # metadata={'source': '/path/to/file.pdf', 'page': 0}
    return splits

def get_collection_status():
    """
    Returns a status message about the current Qdrant collection.
    Used to show users if a collection is already loaded.
    """
    try:
        client = get_qdrant_client()
        collection_name = "my_documents"

        collections = client.get_collections().collections
        collection_names = [col.name for col in collections]

        if collection_name in collection_names:
            collection_info = client.get_collection(collection_name)
            point_count = collection_info.points_count
            return f"✅ Collection loaded: {point_count} document chunks available for RAG"
        else:
            return "No file uploaded yet..."
    except Exception:
        return "No file uploaded yet..."

def load_existing_vectorstore():
    """
    Loads an existing Qdrant collection if it exists.

    Returns:
        QdrantVectorStore if collection exists, None otherwise
    """
    client = get_qdrant_client()
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    collection_name = "my_documents"

    try:
        # Check if collection exists
        collections = client.get_collections().collections
        collection_names = [col.name for col in collections]

        if collection_name in collection_names:
            # Collection exists, connect to it
            vectorstore = QdrantVectorStore(
                client=client,
                collection_name=collection_name,
                embedding=embeddings,
            )

            # Get collection info to show document count
            collection_info = client.get_collection(collection_name)
            point_count = collection_info.points_count

            print(f"✅ Loaded existing collection '{collection_name}' with {point_count} vectors")
            return vectorstore
        else:
            print(f"ℹ️ No existing collection found")
            return None
    except Exception as e:
        print(f"⚠️ Error loading existing collection: {e}")
        return None

def get_uploaded_files():
    """
    Returns a list of all uploaded files with their chunk counts.

    Returns:
        list[dict]: List of files with metadata
                   [{"filename": "file.pdf", "chunks": 50, "source": "/path/to/file.pdf"}, ...]
    """
    try:
        client = get_qdrant_client()
        collection_name = "my_documents"

        # Check if collection exists
        collections = client.get_collections().collections
        collection_names = [col.name for col in collections]

        if collection_name not in collection_names:
            return []

        # Scroll through all points to get unique sources
        offset = None
        all_points = []

        while True:
            result = client.scroll(
                collection_name=collection_name,
                limit=100,
                offset=offset,
                with_payload=True,
                with_vectors=False
            )

            points, next_offset = result
            all_points.extend(points)

            if next_offset is None:
                break
            offset = next_offset

        # Group by source file
        file_chunks = {}
        for point in all_points:
            if point.payload and "metadata" in point.payload:
                source = point.payload["metadata"].get("source", "Unknown")
                if source not in file_chunks:
                    file_chunks[source] = 0
                file_chunks[source] += 1

        # Convert to list format
        files = []
        for source, count in file_chunks.items():
            import os
            filename = os.path.basename(source)
            files.append({
                "filename": filename,
                "chunks": count,
                "source": source
            })

        # Sort by filename
        files.sort(key=lambda x: x["filename"])

        return files

    except Exception as e:
        print(f"⚠️ Error getting uploaded files: {e}")
        return []

def delete_file_from_vectorstore(source_path):
    """
    Deletes all chunks from a specific file.

    Args:
        source_path: The source path of the file to delete

    Returns:
        str: Status message
    """
    try:
        client = get_qdrant_client()
        collection_name = "my_documents"

        # Get filename for message
        import os
        filename = os.path.basename(source_path)

        # Delete points with matching source
        # First, scroll to find all matching point IDs
        offset = None
        points_to_delete = []

        while True:
            result = client.scroll(
                collection_name=collection_name,
                limit=100,
                offset=offset,
                with_payload=True,
                with_vectors=False
            )

            points, next_offset = result

            # Find points with matching source
            for point in points:
                if point.payload and "metadata" in point.payload:
                    if point.payload["metadata"].get("source") == source_path:
                        points_to_delete.append(point.id)

            if next_offset is None:
                break
            offset = next_offset

        if not points_to_delete:
            return f"⚠️ No chunks found for {filename}"

        # Delete the points
        client.delete(
            collection_name=collection_name,
            points_selector=points_to_delete
        )

        deleted_count = len(points_to_delete)
        print(f"🗑️ Deleted {deleted_count} chunks from {filename}")

        # Get updated total
        collection_info = client.get_collection(collection_name)
        remaining = collection_info.points_count

        return f"✅ Deleted {filename} ({deleted_count} chunks). Remaining: {remaining} chunks"

    except Exception as e:
        error_msg = f"⚠️ Error deleting file: {e}"
        print(error_msg)
        return error_msg

def clear_vectorstore():
    """
    Deletes the entire Qdrant collection and all documents.
    Use this to start fresh or clean up old documents.

    Returns:
        str: Status message
    """
    try:
        client = get_qdrant_client()
        collection_name = "my_documents"

        # Delete the collection
        client.delete_collection(collection_name)
        print(f"🗑️ Deleted collection: {collection_name}")

        return f"✅ Collection cleared. All documents removed."
    except Exception as e:
        error_msg = f"⚠️ Error clearing collection: {e}"
        print(error_msg)
        return error_msg

def create_vectorstore(splits):
    """
    Adds documents to existing Qdrant collection (ACCUMULATE MODE).

    If collection doesn't exist, creates it.
    Documents from multiple files are kept together in one collection.
    Use clear_vectorstore() to remove all documents.
    """
    # Get the reusable client
    client = get_qdrant_client()

    # Initialize embeddings
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

    # Collection name
    collection_name = "my_documents"

    # Check if collection exists
    collections = client.get_collections().collections
    collection_names = [col.name for col in collections]

    if collection_name not in collection_names:
        # Collection doesn't exist - create it
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=1536,  # Dimension for text-embedding-3-small
                distance=Distance.COSINE  # Cosine similarity (standard for semantic search)
            )
        )
        print(f"✅ Created new collection: {collection_name}")
    else:
        print(f"📚 Using existing collection: {collection_name}")

    # Connect to collection (existing or new)
    vectorstore = QdrantVectorStore(
        client=client,
        collection_name=collection_name,
        embedding=embeddings,
    )

    # Add documents (doesn't delete existing ones!)
    vectorstore.add_documents(splits)

    # Get total count after adding
    collection_info = client.get_collection(collection_name)
    total_count = collection_info.points_count

    print(f"✅ Added {len(splits)} new chunks. Total in collection: {total_count}")

    return vectorstore
