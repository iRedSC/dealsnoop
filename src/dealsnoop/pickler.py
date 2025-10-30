import pickle
import os
from dealsnoop.logger import logger

class ObjectStore:
    """
    A class to store and retrieve a set of objects using pickling.
    """

    def __init__(self, filename: str):
        """
        Initializes the ObjectStore.

        Args:
            filename (str): The name of the file to use for pickling.
        """
        self.filename = filename
        self.objects = set()
        self._load_objects() # Load existing objects on initialization

    def add_object(self, obj):
        """
        Adds an object to the store.

        Args:
            obj: The object to add. Must be picklable.
        """
        self.objects.add(obj)
        self._save_objects()

    def remove_object(self, obj):
        """
        Removes an object from the store.

        Args:
            obj: The object to remove.
        """
        if obj in self.objects:
            self.objects.remove(obj)
            self._save_objects()
        else:
            logger.warning(f"Warning: Object {obj} not found in the store.")

    def get_all_objects(self):
        """
        Retrieves all objects currently in the store.

        Returns:
            set: A set containing all stored objects.
        """
        return self.objects.copy() # Return a copy to prevent external modification

    def clear_store(self):
        """
        Clears all objects from the store and deletes the pickle file.
        """
        self.objects.clear()
        if os.path.exists(self.filename):
            os.remove(self.filename)
            logger.info(f"Store cleared and file $M$'{self.filename}'$W$ deleted.")
        else:
            logger.info("Store cleared, but no pickle file existed to delete.")

    def _save_objects(self):
        """
        Saves the current set of objects to the specified file using pickling.
        """
        try:
            with open(self.filename, 'wb') as f:
                pickle.dump(self.objects, f)
            logger.info(f"Objects saved to '{self.filename}'.")
        except Exception as e:
            logger.error(f"Error saving objects: $R${e}")

    def _load_objects(self):
        """
        Loads objects from the specified file using unpickling.
        If the file does not exist, an empty set is initialized.
        """
        if os.path.exists(self.filename):
            try:
                with open(self.filename, 'rb') as f:
                    self.objects = pickle.load(f)
                logger.info(f"Objects loaded from '{self.filename}'.")
            except Exception as e:
                logger.error(f"Error loading objects from '{self.filename}': {e}")
                self.objects = set() # Initialize an empty set on error
        else:
            logger.info(f"No existing store file '{self.filename}' found. Starting with an empty store.")
            self.objects = set()