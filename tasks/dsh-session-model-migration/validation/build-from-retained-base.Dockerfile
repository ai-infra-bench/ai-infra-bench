FROM sha256:e87af67674c9b180ee88328bffd4b4279c1324c0567ac86be943f951287a2b0a
WORKDIR /workspace/deepseek-harness
RUN npm run build
COPY . /tests
RUN chmod -R a+rX /tests
