FROM node:24-alpine

WORKDIR /app

COPY ui/package*.json ./
RUN npm install

COPY ui ./

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
