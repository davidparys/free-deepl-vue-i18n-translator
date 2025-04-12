from setuptools import setup, find_packages

setup(
    name="deepl-translator",
    version="0.1.0",
    py_modules=["deepl_translator"],
    install_requires=[
        "requests>=2.25.1",
        "python-dotenv>=0.19.0",
    ],
    entry_points={
        "console_scripts": [
            "deepl-translator=deepl_translator:main",
        ],
    },
    author="Your Name",
    author_email="your.email@example.com",
    description="DeepL translator for Vue i18n JSON files",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/deepl-translator-vue-i18n",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
) 